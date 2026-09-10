"""The command line: a thin front end over api.py.

Argument groups come from ``mainframe_artifacts.cliargs`` so every tool in the family
spells ``--outdir``, ``--no-fetch``, ``--from-bundle``, ``--gather-only`` and ``--jobs``
identically.

CLI output is plain ASCII throughout. The Windows console is cp1252 and an arrow or an em
dash printed from here is a hard crash, not a mangled glyph.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import List, Optional, Tuple

from mainframe_artifacts.artifact_service import load_fetcher
from mainframe_artifacts.bundle import EstateBundle
from mainframe_artifacts.cliargs import (add_logging_args, add_output_args,
                                         add_dependents_args, add_retrieval_args,
                                         dependents_lookup, jobs as _jobs)
from mainframe_artifacts.errors import CobolXstateError
from mainframe_artifacts.logging_setup import configure_logging
from mainframe_artifacts.output import make_run_dir, run_dir, write_json
from mainframe_artifacts.profiling import StageTimer

from .api import analyze, gather, summarize

_log = logging.getLogger(__name__)

CORE_LOGGER = "mainframe_artifacts"
PACKAGE_LOGGER = "cics_dependencies"

#: The lineage view --bind-jcl reads. Checked by name: pointed at the ARTIFACTS view by
#: mistake, the binding would find no `ddBindings`, bind nothing, and say nothing.
JCL_LINEAGE_FORMAT = "jcl-dependencies-lineage"

# The dependents view is not a --target choice: it is not a view you ask for, it is an
# answer you were given, so it is written exactly when a lookup supplied one - the same
# rule the BMS view follows.
_SUFFIXES = (".csd.artifacts.json", ".csd.lineage.json", ".csd.bms.json",
             ".csd.dependents.json", ".csd.prefetch.json", ".csd.fetch.json")


def build_parser():
    import argparse

    p = argparse.ArgumentParser(
        prog="cics-dependencies",
        description="Parse CICS resource definitions - CSD decks, DFHCSDUP EXTRACT "
                    "output, and decks instream in a JCL job - and report what the "
                    "region wires together: which program a transaction runs, which "
                    "dataset a file name binds, which queue write starts a task, and "
                    "whether any of it is installed.")
    p.add_argument("sources", nargs="+", metavar="SOURCE",
                   help="one or more CSD decks. Several members routinely make up one "
                        "region; each keeps its own name, because which member a row "
                        "came from is output.")
    p.add_argument("--sit", metavar="FILE",
                   help="the region's SIT - macro source, an override deck, or the "
                        "DFHSIP PARM. WITHOUT IT every resource is reported "
                        "'installed: unknown', which is the honest default and not a "
                        "failure: GRPLIST is the only thing that says what is live.")
    p.add_argument("--bind-jcl", metavar="FILE",
                   help="a jcl-dependencies LINEAGE view of the CICS region startup "
                        "job. On a CSD-era estate this corroborates each file's DSNAME; "
                        "on a macro-era one it is the ONLY route to a dataset, because a "
                        "DFHFCT entry carries no DSNAME at all.")
    p.add_argument("--bind-program", metavar="FILE", action="append", default=[],
                   help="a COBOL or assembler artifacts manifest whose unresolved CICS "
                        "rows to close against these definitions. Repeatable. Writes one "
                        "*.bound.json per manifest.")
    p.add_argument("--target", choices=("artifacts", "lineage", "both"), default="both",
                   help="which view to write (default: both)")
    add_retrieval_args(p)
    add_dependents_args(p)
    add_output_args(p, outdir_help="where to write the views and reports (default: out)")
    add_logging_args(p)
    return p


def _read(path_text: str) -> Tuple[str, str]:
    path = Path(path_text)
    return path.name, path.read_text(encoding="utf-8", errors="replace")


def _load_jcl(path_text: str) -> dict:
    lineage = json.loads(Path(path_text).read_text(encoding="utf-8"))
    if lineage.get("format") != JCL_LINEAGE_FORMAT:
        raise CobolXstateError(
            "--bind-jcl {0}: this is not a jcl-dependencies LINEAGE view (its 'format' "
            "is {1!r}). The binding reads 'ddBindings', which only that view carries - "
            "point it at the *.jcl.lineage.json a jcl-dependencies run wrote.".format(
                path_text, lineage.get("format")))
    return lineage


def _service(args, source_name: str):
    """The estate artifact service for this run, and why it is missing if it is.

    Never fatal. A run without the service still parses what it was given and still writes
    its reports - they simply say, per member, that nothing was ever looked for.
    """
    fetcher, why = load_fetcher(args.copybook_fetcher)
    if fetcher is None:
        _log.warning("[{0}] WARNING: {1}".format(source_name, why))
    return fetcher, why


def _run(args, timing_sink=None) -> int:
    sources = [_read(path) for path in args.sources]
    source_name = sources[0][0]
    sit = _read(args.sit) if args.sit else None
    timer = StageTimer(_log, args.timing, source_name, sink=timing_sink)

    jcl_lineage = _load_jcl(args.bind_jcl) if args.bind_jcl else None

    bundle = EstateBundle.load(args.from_bundle) if args.from_bundle else None
    fetcher, why_service = (None, None) if bundle is not None \
        else _service(args, source_name)

    out_dir = run_dir(args.outdir)
    err = make_run_dir(out_dir)
    if err:
        _log.error("error: {0}".format(err))
        return 2
    deps = str(out_dir / "deps")

    if args.gather_only:
        gathered = gather(sources, sit=sit, source_name=source_name, fetcher=fetcher,
                          dest=args.gather_only, unavailable=why_service,
                          jobs=_jobs(args))
        _log.info("[{0}] wrote estate bundle {1}".format(source_name, gathered))
        _log.info("[{0}] model from it with: --from-bundle {1}".format(
            source_name, args.gather_only))
        timer.report()
        return 0

    reverse, why_dependents = dependents_lookup(args)
    if why_dependents:
        _log.error("error: {0}".format(why_dependents))
        return 2

    analysis = analyze(sources, sit=sit, source_name=source_name, bundle=bundle,
                       fetcher=fetcher, retrieve=not args.no_fetch, dest=deps,
                       unavailable=why_service, jcl_lineage=jcl_lineage,
                       jobs=_jobs(args), timer=timer,
                       dependents=reverse.mapping if reverse is not None else None,
                       dependents_resolver=(reverse.resolver if reverse is not None
                                            else None))

    base = Path(source_name).stem
    wanted = set({"both": ("artifacts", "lineage")}.get(args.target, (args.target,)))
    written = {
        ".csd.artifacts.json": analysis.artifacts() if "artifacts" in wanted else None,
        ".csd.lineage.json": analysis.lineage() if "lineage" in wanted else None,
        ".csd.bms.json": analysis.bms(),
        # None when no door was opened, and the loop below writes nothing for a None.
        ".csd.dependents.json": analysis.dependents(),
        ".csd.prefetch.json": analysis.prefetch.report(),
        ".csd.fetch.json": analysis.fetch,
    }
    for suffix in _SUFFIXES:
        obj = written.get(suffix)
        if obj is None:
            continue
        target = out_dir / "{0}{1}".format(base, suffix)
        write_json(target, obj, args.indent)
        _log.info("[{0}] wrote {1}".format(source_name, target))

    for path_text in args.bind_program:
        manifest = json.loads(Path(path_text).read_text(encoding="utf-8"))
        bound = analysis.bind(manifest)
        target = out_dir / "{0}.bound.json".format(Path(path_text).stem)
        write_json(target, bound, args.indent)
        _log.info("[{0}] bound {1} of {2} CICS row(s) from {3} -> {4}".format(
            source_name, bound["cicsBinding"]["bound"],
            bound["cicsBinding"]["bound"] + len(bound["cicsBinding"]["unbound"]),
            path_text, target))

    for gap in analysis.unread_bundles():
        _log.warning("[{0}] BUNDLE {1} points at {2}, which was not read - {3}".format(
            source_name, gap["bundle"], gap["bundledir"], gap["reason"]))

    if args.summary:
        for line in summarize(analysis):
            _log.warning(line)

    timer.report()
    return 0


def run(argv: Optional[List[str]] = None, timing_sink=None) -> int:
    """Parse args, configure logging, and dispatch, behind the top-level error boundary."""
    args = build_parser().parse_args(argv)
    # BOTH roots: retrieval logs from mainframe_artifacts.*, everything else from
    # cics_dependencies.*. A root nobody configures propagates to the root logger, or
    # prints WARNING+ via logging's lastResort - which would end -qq's silence.
    configure_logging(verbose=args.verbose or (1 if args.debug else 0), quiet=args.quiet,
                      loggers=(CORE_LOGGER, PACKAGE_LOGGER))
    try:
        return _run(args, timing_sink=timing_sink)
    except CobolXstateError as exc:
        _log.error("error: {0}".format(exc))
        return 2
    except FileNotFoundError as exc:
        _log.error("error: {0}".format(exc))
        return 2
    except ValueError as exc:
        _log.error("error: not readable JSON ({0})".format(exc))
        return 2
    except Exception:
        if args.debug:
            raise
        _log.error("error: an unexpected internal error occurred; re-run with --debug "
                   "for the traceback")
        return 1


def main() -> None:
    import sys
    sys.exit(run())
