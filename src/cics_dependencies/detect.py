"""Which kind of definition source this is, and where inside it the deck actually starts.

The second half of that is not a refinement. A DFHCSDUP deck is very often not a file of
``DEFINE`` statements at all - it is a **whole JCL job** with the deck instream after
``//SYSIN DD *``. IBM's own example-health-apis ships it that way, with forty lines of job
card, copyright notice and ``// SET`` before the first ``Remove``. Handed to the CSD lexer
whole, every one of those lines is noise, and the flags that report them bury the flags
that matter.

So the JCL wrapper is recognised and stripped here. Deliberately in a few lines rather than
by importing ``jcl_dependencies``: this needs to find one instream block, not to model a
job, and the five packages are peers that never import each other.

**Line numbers survive the strip.** Non-deck lines are replaced by blank lines rather than
removed, so every statement still reports the line it occupies in the file the user has
open. A deck extracted by slicing reports line 3 for something on line 47, which is worse
than not reporting a line at all - it sends the reader to the wrong place with confidence.
"""

from __future__ import annotations

import re
from typing import List, Tuple

_JCL_STATEMENT = re.compile(r"^//\*|^//\S*\s+(JOB|EXEC|DD|SET|IF|INCLUDE|PROC|PEND)\b",
                            re.I)
_EXEC_PGM = re.compile(r"^//(?P<step>\S*)\s+EXEC\s+.*?\bPGM=(?P<pgm>[A-Z0-9$#@]+)", re.I)
# `\b` after the `*` would NEVER match: a word boundary needs a word character on one
# side, and `//SYSIN DD *` has a non-word `*` against end-of-line. The alternatives
# therefore get their own terminators.
_INSTREAM_DD = re.compile(r"^//(?P<dd>\S+)\s+DD\s+(?P<kind>\*(?=\s|,|$)|DATA\b)", re.I)

#: The utility whose SYSIN is a CSD deck. A job can hold several steps and only some of
#: them are ours.
CSD_UTILITY = "DFHCSDUP"

#: The assemblers a macro table deck is fed to. A table deck is nearly always shipped as an
#: ASSEMBLE-AND-LINK JOB with the deck instream, not as a bare member: KICKS's own
#: PCT/PPT/FCT/SIT are each a complete `PGM=IFOX00` job. Handed the job whole, the lexer
#: reads forty lines of JCL as assembler statements and the deck itself as continuation
#: text.
ASSEMBLERS = ("IFOX00", "ASMA90", "IEV90", "IEUASM", "ASMBLR")


def looks_like_jcl(text: str) -> bool:
    """Does this source begin as a JCL job rather than as a deck?

    Judged on the first few statement-shaped lines, not on the whole file: the instream
    deck that follows is not JCL and would dilute a whole-file ratio.
    """
    for line in text.splitlines():
        if not line.strip():
            continue
        return bool(_JCL_STATEMENT.match(line))
    return False


def instream_deck(text: str, programs: Tuple[str, ...],
                  what: str) -> Tuple[str, List[str]]:
    """Return (deck, flags): the instream SYSIN of every step running one of ``programs``.

    Blank lines stand in for everything that is not deck, so a statement's line number is
    still its line number in the original file.
    """
    flags: List[str] = []
    lines = text.splitlines()
    kept = [""] * len(lines)

    step_pgm = ""
    capturing = False
    capture_dd = ""
    other_instream: List[str] = []

    for i, line in enumerate(lines):
        if capturing:
            # Instream data ends at /* or at the next JCL statement.
            if line.startswith("/*") or line.startswith("//"):
                capturing = False
            else:
                if step_pgm.upper() in programs:
                    kept[i] = line
                continue

        exec_match = _EXEC_PGM.match(line)
        if exec_match:
            step_pgm = exec_match.group("pgm")
            continue

        dd_match = _INSTREAM_DD.match(line)
        if dd_match:
            capturing = True
            capture_dd = dd_match.group("dd").upper()
            if step_pgm.upper() not in programs:
                other_instream.append("%s at line %d (step runs %s)"
                                      % (capture_dd, i + 1, step_pgm or "an unnamed step"))
            elif capture_dd != "SYSIN":
                flags.append(
                    "line %d: instream data on %s of a %s step was read as deck input - "
                    "the deck is normally on SYSIN" % (i + 1, capture_dd, what))

    deck = "\n".join(kept)
    if not deck.strip():
        flags.append(
            "this source is JCL but no instream deck was found on a %s step; nothing was "
            "parsed. Instream data seen elsewhere: %s"
            % (what, "; ".join(other_instream) or "none"))
    elif other_instream:
        flags.append(
            "instream data on steps that do not run %s was ignored: %s"
            % (what, "; ".join(other_instream)))
    return deck, flags


def csd_deck_from_jcl(text: str) -> Tuple[str, List[str]]:
    """The DFHCSDUP SYSIN inside a job."""
    return instream_deck(text, (CSD_UTILITY,), CSD_UTILITY)


def csd_source(text: str) -> Tuple[str, List[str]]:
    """The deck to parse, whether it arrived bare or wrapped in a job."""
    if looks_like_jcl(text):
        return csd_deck_from_jcl(text)
    return text, []


def macro_deck_source(text: str) -> Tuple[str, List[str]]:
    """The macro deck to parse, whether bare or instream in an assemble job.

    A table deck is nearly always the second: KICKS ships its PCT, PPT, FCT and SIT as four
    complete ``PGM=IFOX00`` jobs. Passed the job whole, the assembler lexer reads the JCL
    as statements, finds no table macro, and reports a deck that contributed nothing.
    """
    if looks_like_jcl(text):
        return instream_deck(text, ASSEMBLERS, "an assembler")
    return text, []


# --------------------------------------------------------------------------- #
# which of the five kinds a source is
# --------------------------------------------------------------------------- #

KIND_CSD = "csd"
KIND_MACRO = "macro-table"
KIND_BMS = "bms"
KIND_BAS = "bas"
KIND_BUNDLE = "bundle"
KIND_SIT = "sit"

# The prefix alternation is not decoration: KICKS spells the same tables KIKPCT / KIKPPT /
# KIKFCT / KIKSIT, and a shop that wraps IBM's macros in its own does the same thing again.
# Keyed on DFH alone, a whole estate's tables detect as "not a macro deck".
_MACRO_NAMES = re.compile(
    r"^\s*\S*\s+((DFH|KIK)(PCT|PPT|FCT|DCT|TCT|TST|PLT|XLT)|DSNCRCT)\b", re.I | re.M)
_BMS_NAMES = re.compile(r"^\s*\S*\s+(DFHMSD|DFHMDI|DFHMDF)\b", re.I | re.M)
_SIT_NAMES = re.compile(r"^\s*\S*\s+(DFH|KIK)SIT\b|^\s*GRPLIST\s*=", re.I | re.M)
_BAS_CREATE = re.compile(r"^\s*CREATE\s+[A-Z0-9]+DEF\b", re.I | re.M)
_CSD_DEFINE = re.compile(r"^\s*(DEFINE|ADD|USERDEFINE)\s", re.I | re.M)


def source_kind(text: str, source_name: str = "") -> str:
    """Which parser this source belongs to.

    By CONTENT first and name second, because members arrive from an estate service under
    whatever name the library gave them. The order matters: a BMS deck and a macro table
    deck are both assembler and both start with a label in column 1, so they are told apart
    by which macros they invoke, never by their suffix.

    A source that looks like none of these comes back ``KIND_CSD``, which is the one whose
    parser reports what it did not understand rather than silently producing nothing.
    """
    if text.lstrip().startswith("<?xml") or "<manifest" in text[:2000]:
        return KIND_BUNDLE
    if _BMS_NAMES.search(text):
        return KIND_BMS
    if _MACRO_NAMES.search(text):
        return KIND_MACRO
    if _BAS_CREATE.search(text):
        return KIND_BAS
    if _CSD_DEFINE.search(text):
        return KIND_CSD
    # The SIT is checked BEFORE the JCL fallback: KICKS ships its SIT as an assemble job,
    # and a job with no DEFINE in it would otherwise be handed to the CSD parser, which
    # would find no commands and report a deck that contributed nothing.
    if _SIT_NAMES.search(text):
        return KIND_SIT
    return KIND_CSD
