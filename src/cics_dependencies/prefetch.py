"""Stage 1 for CICS: close over the LISTs, GROUPs and table members a region needs.

The same replay-until-quiet shape as the JCL side's PROC/INCLUDE closure and the assembler
side's COPY/macro closure, and for the same reason: a source parsed without what it names
reads as far simpler than it is. What differs is the QUESTION being replayed.

A CSD deck does not textually include anything, so there is no parser resolver to record.
What is incomplete is the MODEL: the SIT's ``GRPLIST`` names LISTs this deck may not
contain, a LIST names GROUPs whose definitions may be in another member, and a macro-era
SIT names ``DFHPCT``/``DFHFCT`` decks by suffix. So the closure asks the region what it is
missing, retrieves that, parses it in, and asks again.

**A group that is named but not in hand is the whole point.** Without the closure its
resources are absent, and absent reads exactly like "the group is empty" - a region that
installs forty groups and holds definitions for three looks like a small region rather than
a badly-supplied model. ``install.py`` already flags the gap; this is what closes it.

**Nothing here guesses at a name.** A LIST, a GROUP and a ``DFHPLTPI`` are all asked for
under exactly the name the source wrote. A not-found is reported as a not-found - it means
the estate was asked and had nothing, which is a fact about the estate and not about this
parse.
"""

from __future__ import annotations

from typing import Callable, Iterable, List, Optional, Tuple

from mainframe_artifacts.prefetch import (PrefetchResult, Prefetcher,  # noqa: F401
                                          member_key)

from .classify import is_ibm_group
from .csd import parse_csd
from .install import installed_groups
from .model import Region
from .sit import parse_sit, table_members

#: What the estate is asked for each kind of gap. CSD material is type ``csd``; a macro-era
#: table deck is assembler, and asking for it as ``csd`` would have the service hand back
#: the wrong member (or nothing) without either side noticing.
_TYPE_CSD = "csd"
_TYPE_ASM = "asm"


def _wants(region: Region) -> List[Tuple[str, str, str]]:
    """(name, type, why) for everything this region names but does not hold."""
    wants: List[Tuple[str, str, str]] = []

    have_lists = set(region.lists)
    for name in region.grplist:
        if name in have_lists or is_ibm_group(name):
            # DFHLIST is in every real GRPLIST and holds CICS's own definitions. Asking
            # the estate for it spends a round-trip to retrieve several hundred rows this
            # package would then exclude as ibm-runtime anyway - and a not-found against
            # it reads as a gap in the shop's model, which it is not.
            continue
        wants.append((name, _TYPE_CSD,
                      "named by the SIT's GRPLIST; its groups are unaccounted for "
                      "until it is in hand"))

    reached, _ = installed_groups(region)
    have_groups = {res.group for res in region.resources if res.group}
    for group in sorted(reached - have_groups):
        wants.append((group, _TYPE_CSD,
                      "a LIST adds this group and no definition in it has been seen, so "
                      "its resources are missing rather than absent"))

    for parameter, member, why in table_members(region):
        wants.append((member, _TYPE_ASM, why))

    return wants


def _absorb(region: Region, name: str, text: str) -> None:
    """Parse a retrieved member into the region, choosing by what it looks like.

    A ``DFHSIT`` member amends the SIT; anything else is read as a deck. Getting this
    wrong is not silent - a SIT read as a CSD deck yields no resources and a flag saying
    the commands were unrecognised.
    """
    if name.upper().startswith("DFHSIT"):
        parse_sit(text, source_name=name, region=region)
    else:
        parse_csd(text, source_name=name, region=region)


def prefetch_cics(region: Region, fetcher: Optional[Callable],
                  paths: Optional[List[str]] = None, dest: Optional[str] = None,
                  source_name: str = "<csd>", max_rounds: int = 12,
                  unavailable: Optional[str] = None,
                  result: Optional[PrefetchResult] = None,
                  jobs: int = 1,
                  seen: Optional[Iterable[str]] = None,
                  producer: Optional[str] = None) -> PrefetchResult:
    """Retrieve what ``region`` names and does not hold, parsing each round in.

    Mutates ``region``. Returns the retrieval report, which is the honest account of what
    was asked for and what came back - a not-found here is a real hole in the model and
    every view downstream should be read against it.
    """
    pf = Prefetcher(fetcher, paths, dest, unavailable, result, seen=seen,
                    producer=producer)
    pf.name_source(source_name)

    for _ in range(max_rounds):
        fresh = [(name, type_hint, why) for name, type_hint, why in _wants(region)
                 if member_key(name) not in pf.seen]
        if not fresh:
            break
        # One round IS a level: nothing in this wave can name what another member of it
        # holds until that member has been read, so the whole wave is asked for at once.
        # Grouped by type because the estate is told what kind of member to look for.
        for type_hint in (_TYPE_CSD, _TYPE_ASM):
            wave = [(name, why) for name, hint, why in fresh if hint == type_hint]
            if not wave:
                continue
            for name, text in pf.obtain_wave(wave, type_hint, jobs):
                if text:
                    _absorb(region, name, text)
    else:
        pf.note_closure_bound(max_rounds)

    return pf.result
