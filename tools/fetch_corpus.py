"""Download the public CICS corpus this package is validated against.

Examples written for this repository only prove the tool does what it was built to do. The
corpus is real CICS material from public repositories, and it is NOT committed here - it is
third-party, and a vendored copy rots. This downloads it into ``corpus/``, which
``.gitignore`` covers, and the corpus tests skip cleanly when it is absent.

    python tools/fetch_corpus.py            # fetch into ./corpus
    python tools/fetch_corpus.py --check    # report what is present, fetch nothing

Same arrangement asm-dependencies used for IFOX and learnasm370.
"""

from __future__ import annotations

import argparse
import sys
import urllib.request
from pathlib import Path

CORPUS = Path(__file__).resolve().parents[1] / "corpus"

#: local name -> (url, what it is, what it proves)
SOURCES = {
    "CARDDEMO.CSD": (
        "https://raw.githubusercontent.com/aws-samples/"
        "aws-mainframe-modernization-carddemo/main/app/csd/CARDDEMO.CSD",
        "AWS CardDemo, Apache 2.0",
        "64 real DEFINEs - FILE with DSNAME, TRANSACTION with PROGRAM, MAPSET, LIBRARY "
        "with DSNAME01, TDQUEUE with DDNAME. The COBOL and JCL that use them are in the "
        "same repository, so both ends of every binder are checkable.",
    ),
    "HCAZ.CSDUP.JCL": (
        "https://raw.githubusercontent.com/IBM/example-health-apis/master/"
        "HCAZ_Source/IBMUSER.ZMOBILE.JCL/.expanded/%40CDEF121.JCL",
        "IBM example-health-apis, Apache 2.0",
        "What CardDemo lacks: REMOVE/DELETE/ADD GROUP...LIST, the group-to-list "
        "membership the install closure needs. Also mixed case, which CardDemo alone "
        "would have hidden from the lexer.",
    ),
    # The macro-table era, at last. KICKS is a CICS-compatible system and its tables are
    # the same shape as IBM's, spelt KIKPCT/KIKPPT/KIKFCT/KIKSIT. NOT redistributable -
    # DOGECICS carries no licence file - which is another reason the corpus is fetched
    # rather than vendored.
    "KIKPCTDO.jcl": (
        "https://raw.githubusercontent.com/mainframed/DOGECICS/main/SIT/KIKPCTDO",
        "DOGECICS / KICKS, no licence stated",
        "A real PCT: entries with a label, entries without, and - the find - an HLASM "
        "REMARK after the operands ('PROGRAM=KSGMPGM NO REFRESH'), which read as operand "
        "text makes the program name 'KSGMPGM NO REFRESH'.",
    ),
    "KIKPPTDO.jcl": (
        "https://raw.githubusercontent.com/mainframed/DOGECICS/main/SIT/KIKPPTDO",
        "DOGECICS / KICKS, no licence stated",
        "A real PPT, in which a MAPSET is spelt 'PROGRAM=KSGMAP,USAGE=MAP' rather than "
        "MAPSET= - so a parser keyed on the operand name reports every map as a program.",
    ),
    "KIKFCTDO.jcl": (
        "https://raw.githubusercontent.com/mainframed/DOGECICS/main/SIT/KIKFCTDO",
        "DOGECICS / KICKS, no licence stated",
        "A real FCT: DATASET= entries with no DSNAME anywhere, which is the whole reason "
        "bind_jcl_region exists. Continued with '*' in column 72 rather than 'X'.",
    ),
    "KIKSITDO.jcl": (
        "https://raw.githubusercontent.com/mainframed/DOGECICS/main/SIT/KIKSITDO",
        "DOGECICS / KICKS, no licence stated",
        "A real SIT, which neither CSD corpus member has - and the one thing that makes "
        "the `installed` axis testable against something other than a fixture written "
        "here. Names its tables by suffix (PCT=DO, PPT=DO, FCT=DO).",
    ),
    "DOGEMMAP.bms": (
        "https://raw.githubusercontent.com/mainframed/DOGECICS/main/BMS/DOGEMMAP",
        "DOGECICS, no licence stated",
        "A real BMS mapset - 60KB of DFHMSD/DFHMDI/DFHMDF with heavy continuation, "
        "COLOR/ATTRB lists and quoted INITIAL literals containing punctuation.",
    ),
}


def fetch(name: str, url: str) -> int:
    with urllib.request.urlopen(url, timeout=60) as response:
        data = response.read()
    CORPUS.mkdir(parents=True, exist_ok=True)
    (CORPUS / name).write_bytes(data)
    return len(data)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true",
                        help="report what is present without downloading")
    args = parser.parse_args(argv)

    missing = 0
    for name, (url, origin, proves) in sorted(SOURCES.items()):
        path = CORPUS / name
        if args.check:
            if path.is_file():
                print("present  %-18s %7d bytes  (%s)" % (name, path.stat().st_size,
                                                          origin))
            else:
                missing += 1
                print("MISSING  %-18s  %s" % (name, origin))
                print("         %s" % proves)
            continue
        try:
            size = fetch(name, url)
        except Exception as exc:                      # noqa: BLE001 - report, don't raise
            missing += 1
            print("FAILED   %-18s %s: %s" % (name, url, exc))
            continue
        print("fetched  %-18s %7d bytes  (%s)" % (name, size, origin))

    if args.check and missing:
        print("\n%d of %d absent - run `python tools/fetch_corpus.py` to get them"
              % (missing, len(SOURCES)))
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
