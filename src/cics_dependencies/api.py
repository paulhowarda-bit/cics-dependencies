"""The CICS front end as a library: analyze definition sources, get the region's views.

The same shape as the COBOL, JCL, Easytrieve and assembler sides' ``api`` modules, and for
the same reason: driving this from another Python program should be the code path the
command line takes, not a second one that drifts from it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import (Any, Callable, Dict, List, Mapping, Optional, Sequence,
                    Tuple)

from mainframe_artifacts.bundle import (EstateBundle, recording_dependents_resolver,
                                        recording_fetcher, write_bundle)
from mainframe_artifacts.dependents import DependentsLookup
from mainframe_artifacts.fetch import fetch_dependencies
from mainframe_artifacts.prefetch import PrefetchResult
from mainframe_artifacts.profiling import StageTimer

from . import PRODUCER
from .bas import parse_bas
from .bms import bind_mapsets, build_bms_lineage, parse_bms
from .bundles import bundle_directories, parse_bundle
from .csd import parse_csd
from .detect import (KIND_BAS, KIND_BMS, KIND_BUNDLE, KIND_MACRO, KIND_SIT, source_kind)
from .install import apply_install_state
from .model import Region
from .prefetch import prefetch_cics
from .sit import parse_sit
from .tables import parse_tables
from .views import (bind_jcl_region, bind_program_artifacts, build_cics_artifacts,
                    build_cics_dependents, build_cics_lineage)

_log = logging.getLogger(__name__)


@dataclass
class RegionAnalysis:
    """One analyzed region - however many decks and SITs went into it - and its views."""

    region: Region
    prefetch: PrefetchResult
    source_name: str = "<csd>"
    fetch: Optional[dict] = None
    #: Parsed BMS mapsets, if any BMS source was supplied. Kept apart from the region on
    #: purpose: a mapset is a screen layout, not a CSD resource.
    mapsets: List = field(default_factory=list)
    #: What the estate says depends on the resources these definitions provide - None
    #: when the run opened neither door, and then :meth:`dependents` is None too, for the
    #: same reason :meth:`bms` is.
    dependents_lookup: Optional[DependentsLookup] = None

    _lineage: Optional[dict] = field(default=None, repr=False)
    _artifacts: Optional[dict] = field(default=None, repr=False)
    _dependents: Optional[dict] = field(default=None, repr=False)

    def artifacts(self) -> dict:
        """The manifest: what these sources define, and everything they name."""
        if self._artifacts is None:
            self._artifacts = build_cics_artifacts(self.region)
        return self._artifacts

    def lineage(self) -> dict:
        """The wiring: what starts work here, what it runs, and what nothing starts."""
        if self._lineage is None:
            self._lineage = build_cics_lineage(self.region)
        return self._lineage

    def bms(self) -> Optional[dict]:
        """The field view, when BMS source was supplied. ``None`` when none was.

        ``None`` rather than an empty view: "no BMS was given" and "the maps have no
        fields" are different statements, and only the first is usually true.
        """
        return build_bms_lineage(self.mapsets) if self.mapsets else None

    def dependents(self) -> Optional[dict]:
        """What depends on the resources defined here, or ``None`` if nobody was asked.

        ``None`` rather than an empty view, the same distinction :meth:`bms` draws: an
        empty answer would read as "nothing in the estate depends on these resources",
        which a run that opened no door has no basis for.
        """
        if self.dependents_lookup is None or not self.dependents_lookup.supplied:
            return None
        if self._dependents is None:
            self._dependents = build_cics_dependents(self.region,
                                                     self.dependents_lookup)
        return self._dependents

    def unread_bundles(self) -> List[dict]:
        """BUNDLEDIRs named by the definitions and never read - resources missing from
        this model, listed so a run can say what it did not see."""
        return bundle_directories(self.region)

    def bind(self, program_manifest: dict) -> dict:
        """Close a COBOL or assembler manifest's CICS rows against these definitions.

        Takes a plain dict and returns one - this package never imports a peer.
        """
        return bind_program_artifacts(program_manifest, self.region)

    def bind_jcl(self, jcl_lineage: dict, *, step: Optional[str] = None) -> Region:
        """Bind file names to datasets from the region startup job's DD statements.

        Invalidates the cached views, because it changes them: on a macro-era estate this
        is where every file row's dataset comes from, and a view built before it would be
        the pre-binding one served forever after.
        """
        bind_jcl_region(self.region, jcl_lineage, step=step)
        self._artifacts = self._lineage = None
        return self.region


def analyze(sources: Sequence[Tuple[str, str]], *,
            sit: Optional[Tuple[str, str]] = None,
            source_name: Optional[str] = None,
            bundle: Optional[EstateBundle] = None,
            fetcher: Optional[Any] = None,
            retrieve: bool = True,
            paths: Sequence[str] = (), dest: Optional[str] = None,
            unavailable: Optional[str] = None,
            jcl_lineage: Optional[dict] = None,
            max_rounds: int = 12, jobs: int = 1,
            timer: Optional[StageTimer] = None,
            dependents: Optional[Mapping[str, Sequence[dict]]] = None,
            dependents_resolver: Optional[Callable[..., Any]] = None,
            ) -> RegionAnalysis:
    """Parse definition sources into one region, close over what they name, and view it.

    ``sources`` is ``[(name, text), ...]`` - several decks routinely make up one region,
    and which member a row came from is output, so they are named rather than concatenated.

    ``sit`` is this package's ``&SYSPARM``: supply it and every resource gets a real
    ``installed`` state; leave it out and they are all ``unknown``, with one flag saying
    why. Unlike ``&SYSPARM`` it is a whole source, because a region is assembled from
    members rather than decided by a value.

    Stage 1 is not decoration here. A SIT's ``GRPLIST`` names LISTs whose groups may live
    in members this deck does not contain, and a region modelled without them holds
    definitions for a fraction of what it installs - which reads as a small region, not as
    a badly-supplied model.

    The estate is reached the same four ways as everywhere else in the family: through
    ``fetcher``, not at all (``fetcher=None``), deliberately off (``retrieve=False``), or
    replayed from a gathered ``bundle``.
    """
    if not sources:
        raise ValueError("analyze needs at least one (name, text) definition source")
    subject = source_name or sources[0][0]
    timer = timer or StageTimer(_log, False, subject)

    if bundle is not None:
        fetcher = bundle.fetcher()
        unavailable = unavailable or bundle.unavailable
        if dependents_resolver is None and bundle.has_dependents():
            dependents_resolver = bundle.dependents()
    elif not retrieve:
        fetcher = None
        unavailable = unavailable or ("retrieval was disabled for this run, so this "
                                      "member was never looked for")

    region = Region()
    mapsets: List = []
    with timer.stage("parse"):
        for name, text in sources:
            kind = source_kind(text, name)
            if kind == KIND_MACRO:
                parse_tables(text, source_name=name, region=region)
            elif kind == KIND_BAS:
                parse_bas(text, source_name=name, region=region)
            elif kind == KIND_BUNDLE:
                parse_bundle(text, source_name=name, region=region)
            elif kind == KIND_BMS:
                # A mapset is not a CSD resource - the DEFINE MAPSET that names it is - so
                # BMS goes to its own view and is joined to the definitions, never mixed
                # into them.
                mapsets.extend(parse_bms(text, source_name=name))
            elif kind == KIND_SIT:
                parse_sit(text, source_name=name, region=region)
            else:
                parse_csd(text, source_name=name, region=region)
        if sit is not None:
            parse_sit(sit[1], source_name=sit[0], region=region)
        if mapsets:
            bind_mapsets(region, mapsets)

    # The closure runs AFTER the SIT, because GRPLIST is what says which lists are wanted.
    with timer.stage("prefetch"):
        pre = prefetch_cics(region, fetcher, paths=list(paths), dest=dest,
                            source_name=subject, unavailable=unavailable,
                            max_rounds=max_rounds, jobs=jobs, producer=PRODUCER)

    if jcl_lineage is not None:
        with timer.stage("bind-jcl"):
            bind_jcl_region(region, jcl_lineage)

    with timer.stage("install"):
        apply_install_state(region)

    reverse = (DependentsLookup(dependents, dependents_resolver)
               if (dependents or dependents_resolver is not None) else None)
    analysis = RegionAnalysis(region=region, prefetch=pre, source_name=subject,
                              mapsets=mapsets, dependents_lookup=reverse)
    with timer.stage("cics-artifacts"):
        art = analysis.artifacts()
    with timer.stage("cics-lineage"):
        analysis.lineage()
    if reverse is not None:
        # Built here rather than on demand: building it is what ASKS the host, and a
        # gather run has to make the asks in order to record them.
        with timer.stage("cics-dependents"):
            analysis.dependents()
    with timer.stage("fetch"):
        analysis.fetch = fetch_dependencies(art, fetcher, dest=dest,
                                            prefetched=pre.store,
                                            unavailable=unavailable, jobs=jobs,
                                            producer=PRODUCER)
    return analysis


def gather(sources: Sequence[Tuple[str, str]], *, dest: str,
           sit: Optional[Tuple[str, str]] = None,
           source_name: Optional[str] = None,
           fetcher: Optional[Any] = None,
           paths: Sequence[str] = (),
           unavailable: Optional[str] = None,
           max_rounds: int = 12, jobs: int = 1,
           dependents: Optional[Mapping[str, Sequence[dict]]] = None,
           dependents_resolver: Optional[Callable[..., Any]] = None) -> str:
    """Run the retrieval half where the estate is reachable; return the bundle manifest.

    A dependents lookup is gathered like the artifact service: wrapped in a recorder,
    asked exactly as a live run asks it, and its answers written into the bundle. The
    index is as unreachable from the modelling box as the estate is."""
    recorder, answers = recording_fetcher(fetcher) if fetcher is not None else (None, [])
    reverse, reverse_answers = (recording_dependents_resolver(dependents_resolver)
                                if dependents_resolver is not None else (None, []))
    analysis = analyze(sources, sit=sit, source_name=source_name, fetcher=recorder,
                       paths=paths, dest=dest, unavailable=unavailable,
                       max_rounds=max_rounds, jobs=jobs, dependents=dependents,
                       dependents_resolver=reverse)
    subject = source_name or sources[0][0]
    text = next((t for n, t in sources if n == subject), sources[0][1])
    return write_bundle(dest, subject_name=subject, subject_text=text,
                        kind="csd", prefetch=analysis.prefetch, answers=answers,
                        fetch=analysis.fetch, dependents=reverse_answers)


def summarize(analysis: RegionAnalysis) -> List[str]:
    """A human scoreboard, INCLUDING the zeros. Plain ASCII: the Windows console is
    cp1252 and an arrow printed from a CLI is a crash, not a mangled glyph."""
    art, lin = analysis.artifacts(), analysis.lineage()
    counts: Dict[str, int] = {}
    for row in art["artifacts"]:
        counts[row["kind"]] = counts.get(row["kind"], 0) + 1
    installed: Dict[str, int] = {}
    for row in art["provides"]:
        installed[row["installed"]] = installed.get(row["installed"], 0) + 1

    out = [
        "region:      %s" % art["region"],
        "sources:     %s" % ", ".join(art["sources"]),
        "defines:     %d resources (%s)"
        % (len(art["provides"]),
           ", ".join("%d %s" % (n, state) for state, n in sorted(installed.items()))
           or "none"),
        "names:       %d artifacts (%s)"
        % (len(art["artifacts"]),
           ", ".join("%d %s" % (n, kind) for kind, n in sorted(counts.items()))
           or "none"),
        "excluded:    %d" % len(art["excluded"]),
        "entry points:%d, unreachable transactions: %d of %d"
        % (len(lin["entryPoints"]), len(lin["unreachable"]), len(lin["transactions"])),
        "flags:       %d" % len(art["flags"]),
    ]
    if analysis.prefetch.missing:
        out.append("NOT RETRIEVED: %s" % ", ".join(analysis.prefetch.missing))
    return out
