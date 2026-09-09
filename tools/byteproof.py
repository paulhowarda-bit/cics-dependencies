#!/usr/bin/env python3
"""Byte-stability ratchet: hash every view of every example, and refuse to let a refactor
change one byte of it.

Output here is a contract, not a rendering: a manifest is read, diffed, joined against a
program's unresolved CICS rows and loaded into a graph. A refactor that should not change
output must produce identical bytes, and a green test run does not prove that - the order
of `touchedBy`, the presence of a `needs`, the wording of a flag and the key order of a
row are all output, and none of them is asserted anywhere.

What is hashed is the EXACT TEXT a run would write - ``json.dumps(obj, indent=2) + "\\n"``
- not a normalized or re-parsed form. A view that reorders its keys, changes its indent or
gains a trailing newline is a changed view, and this must say so.

Every deck is hashed **twice for the SIT**: once with none supplied and once with
``appregn.sit``. That is this package's ``&SYSPARM``. Without a SIT every resource is
``installed: unknown``; with one they are decided - genuinely different output, and a
change that collapsed the two would otherwise be invisible.

The conflicting pair (``appregn.csd`` + ``legacy.csd`` parsed into one region) is hashed
as its own case, because the two-eras rule lives entirely in output wording and has no
other guard.

    python tools/byteproof.py --record goldens/views.sha256
    python tools/byteproof.py --check  goldens/views.sha256
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import traceback
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

REPO = Path(__file__).resolve().parents[1]
EXAMPLES = REPO / "examples"

sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "tests"))

# mainframe-artifacts arrives installed or from the sibling mainframe-common checkout
# (override with MAINFRAME_COMMON_REPO) - the same discovery the test suite performs.
from _mainframe_common import ensure_on_path                        # noqa: E402
_missing = ensure_on_path()
if _missing is not None:
    raise SystemExit("error: {0}".format(_missing))

from cics_dependencies.bas import parse_bas                         # noqa: E402
from cics_dependencies.bms import build_bms_lineage, parse_bms      # noqa: E402
from cics_dependencies.csd import parse_csd                         # noqa: E402
from cics_dependencies.detect import (KIND_BAS, KIND_MACRO,         # noqa: E402
                                      source_kind)
from cics_dependencies.install import apply_install_state           # noqa: E402
from cics_dependencies.sit import parse_sit                         # noqa: E402
from cics_dependencies.tables import parse_tables                   # noqa: E402
from cics_dependencies.views import (bind_jcl_region,               # noqa: E402
                                     bind_program_artifacts,
                                     build_cics_artifacts,
                                     build_cics_lineage)

INDENT = 2  # what a default run would write

#: The SITs every deck is hashed under. ``None`` is the honest default - no SIT supplied,
#: so every resource reports `installed: unknown`.
SITS: Sequence[Optional[str]] = (None, "appregn.sit")

#: Every definition-source suffix in examples/. BMS is hashed separately (a mapset is not
#: a region resource); the region JCL is an input to a binder, not a deck.
DECK_SUFFIXES = (".csd", ".pct")
BMS_SUFFIX = ".bms"

#: Decks parsed together into one region, and why. The conflict rule has no other guard.
COMBINATIONS = {
    "appregn+legacy": ("appregn.csd", "legacy.csd"),
}

#: The deck the committed peer manifest binds against, and that manifest. The bound view
#: is the cross-repository contract's output, and it is the one most worth locking: a
#: manifest nobody managed to bind looks exactly like one nobody tried to bind.
BOUND_EXAMPLE = "custinq.csd"
PEER_MANIFEST = REPO / "tests" / "fixtures" / "custinq.asm.artifacts.json"

#: The deck whose region startup job is committed, and that job's lineage view. Hashing
#: the manifest AFTER bind_jcl_region locks the other cross-repository contract's effect:
#: a corroborated DD, a disagreeing one and an unmatched one all show up in output wording
#: and nowhere else.
REGION_EXAMPLE = "appregn.csd"
JCL_LINEAGE = REPO / "tests" / "fixtures" / "cicsapp1.jcl.lineage.json"


def json_text(obj) -> str:
    return json.dumps(obj, indent=INDENT) + "\n"


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def guarded(build: Callable[[], str]) -> str:
    """A view that stops being produced is exactly the silent loss this exists to catch,
    so an exception is hashed rather than raised."""
    try:
        return build()
    except Exception:
        return "ERROR:\n" + traceback.format_exc(limit=0)


def _region(decks: Sequence[str], sit: Optional[str]):
    """Parse each deck with the parser its CONTENT calls for, exactly as the CLI does.

    Dispatching by ``source_kind`` here rather than always calling ``parse_csd`` matters:
    the macro and BAS paths would otherwise be hashed as "a CSD deck that defines nothing",
    which is stable, wrong, and would go on being stable while they broke.
    """
    region = None
    for deck in decks:
        text = (EXAMPLES / deck).read_text(encoding="utf-8")
        kind = source_kind(text, deck)
        parse = {KIND_MACRO: parse_tables, KIND_BAS: parse_bas}.get(kind, parse_csd)
        region = parse(text, source_name=deck, region=region)
    if sit is not None:
        parse_sit((EXAMPLES / sit).read_text(encoding="utf-8"), source_name=sit,
                  region=region)
    return apply_install_state(region)


def views(decks: Sequence[str], sit: Optional[str]) -> Dict[str, str]:
    out = {
        "cics.artifacts": guarded(
            lambda: json_text(build_cics_artifacts(_region(decks, sit)))),
        "cics.lineage": guarded(
            lambda: json_text(build_cics_lineage(_region(decks, sit)))),
    }
    if BOUND_EXAMPLE in decks and PEER_MANIFEST.is_file():
        peer = json.loads(PEER_MANIFEST.read_text(encoding="utf-8"))
        out["cics.bound"] = guarded(
            lambda: json_text(bind_program_artifacts(peer, _region(decks, sit))))
    if REGION_EXAMPLE in decks and JCL_LINEAGE.is_file():
        lineage = json.loads(JCL_LINEAGE.read_text(encoding="utf-8"))

        def region_bound() -> str:
            region = _region(decks, sit)
            bind_jcl_region(region, lineage)
            return json_text(build_cics_artifacts(region))

        out["cics.artifacts.jclbound"] = guarded(region_bound)
    return out


def build_manifest() -> Dict[str, str]:
    out: Dict[str, str] = {}
    cases = {path.name: (path.name,)
             for path in sorted(EXAMPLES.iterdir())
             if path.suffix.lower() in DECK_SUFFIXES}
    cases.update(COMBINATIONS)
    for case, decks in sorted(cases.items()):
        for sit in SITS:
            label = "sit={0}".format(sit or "-")
            for name, text in views(decks, sit).items():
                out["{0}::{1}::{2}".format(case, label, name)] = digest(text)

    for path in sorted(EXAMPLES.glob("*" + BMS_SUFFIX)):
        text = path.read_text(encoding="utf-8")
        out["{0}::-::cics.bms".format(path.name)] = digest(guarded(
            lambda t=text, n=path.name: json_text(
                build_bms_lineage(parse_bms(t, source_name=n)))))
    return dict(sorted(out.items()))


def dump(manifest: Dict[str, str], path: Path) -> None:
    # newline="\n" explicitly: on Windows the default rewrites every line ending to CRLF,
    # and `.gitattributes` pins this repository to LF because a CRLF checkout changes every
    # hashed byte. A goldens file written CRLF is a file git normalizes on the next commit,
    # which is a diff nobody intended in the one file whose bytes are the contract.
    lines = ["{0}  {1}".format(sha, key) for key, sha in manifest.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def load(path: Path) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        sha, _, key = line.partition("  ")
        out[key] = sha
    return out


def compare(now: Dict[str, str], golden: Dict[str, str]) -> List[str]:
    problems: List[str] = []
    for key in sorted(set(golden) | set(now)):
        if key not in now:
            problems.append("MISSING  {0}".format(key))
        elif key not in golden:
            problems.append("ADDED    {0}".format(key))
        elif now[key] != golden[key]:
            problems.append(
                "CHANGED  {0}\n         golden {1}\n         now    {2}".format(
                    key, golden[key], now[key]))
    return problems


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Hash every view of every example and compare against the goldens.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--record", metavar="FILE",
                       help="rebuild the goldens. DELIBERATELY only - an output change "
                            "must be intended and reviewed before it is recorded.")
    group.add_argument("--check", metavar="FILE", help="compare against the goldens")
    args = parser.parse_args(argv)

    now = build_manifest()
    if args.record:
        path = Path(args.record)
        path.parent.mkdir(parents=True, exist_ok=True)
        dump(now, path)
        print("recorded: {0} view digests -> {1}".format(len(now), path))
        return 0

    path = Path(args.check)
    if not path.is_file():
        print("error: no goldens at {0} - record them first".format(path))
        return 2
    problems = compare(now, load(path))
    if problems:
        print("BYTE-STABILITY FAILURE ({0}):".format(len(problems)))
        for problem in problems:
            print("  " + problem)
        print("\nIf the change was intended and reviewed:"
              "\n  python tools/byteproof.py --record {0}".format(path))
        return 1
    print("byte-stable: {0} view digests match {1}".format(len(now), path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
