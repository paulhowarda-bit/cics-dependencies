"""The System Initialization Table -> the Region's identity and its GRPLIST.

Three places say what a region starts with, and later ones win: ``DFHSIT TYPE=CSECT``
assembler source, a SIT override deck on the ``DFHSIP`` step's SYSIN, and ``PARM=`` on the
``DFHSIP`` EXEC itself. All three are read here by one scanner, because all three are
ultimately ``KEYWORD=value`` and the differences are lexical.

Every parameter is kept verbatim on ``Region.sit`` whether or not it names an artifact.
``MXT``, ``DSALIM`` and ``SEC`` name nothing and are frequently the reason someone opened
the manifest at all.

What is load-bearing:

``GRPLIST``  the LISTs installed at startup. This, and nothing else, is what makes a
             DEFINE an installed resource - see ``install.py``.
``APPLID``   ``SYSIDNT``  the region's identity, and the far end of every REMOTESYSTEM.
``PLTPI``    ``PLTSD``  ``XLT``  suffixes naming DFHPLT/DFHXLT members to retrieve.
``GMTRAN``   the good-morning transaction: an entry point with no caller in any program.
``PCT`` ``PPT`` ``FCT`` ``DCT`` ``TST`` ``RCT``  for a macro-era region, the suffixes
             naming which table decks are live - the macro equivalent of GRPLIST.
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

from .detect import macro_deck_source
from .model import Region

#: Suffix parameters that name a table or list MEMBER rather than a value. ``PLTPI=PI``
#: means the member ``DFHPLTPI``: the parameter carries the last two characters only.
MEMBER_SUFFIX = {
    "PLTPI": "DFHPLT", "PLTSD": "DFHPLT", "XLT": "DFHXLT", "MCT": "DFHMCT",
    "PCT": "DFHPCT", "PPT": "DFHPPT", "FCT": "DFHFCT", "DCT": "DFHDCT",
    "TST": "DFHTST", "TCT": "DFHTCT", "SRT": "DFHSRT", "JCT": "DFHJCT",
    "RCT": "DFHRCT", "SIT": "DFHSIT",
}

#: Values of a suffix parameter that mean "no such table", not a member name.
_NO_TABLE = frozenset({"NO", "NONE", ""})

_KEYWORD = re.compile(r"([A-Z][A-Z0-9]*)\s*=\s*(\([^)]*\)|'[^']*'|[^,\s]*)", re.I)
#: KICKS spells it KIKSIT. Same shape, same parameters, different three letters.
_MACRO_LINE = re.compile(r"^\s*(DFHSIT|KIKSIT)\b", re.I)
_MACRO_NAME = re.compile(r"\b(DFHSIT|KIKSIT)\b", re.I)


def _join_assembler(text: str) -> str:
    """Join column-72 continuations. A SIT macro routinely runs to thirty lines.

    A SIT override deck has no continuations and is unaffected: its lines are short, so
    nothing is ever joined that should not be.
    """
    out: List[str] = []
    joining = False
    for raw in text.splitlines():
        line = raw.rstrip("\r\n")
        if line[:1] == "*":
            continue
        continues = len(line) > 71 and line[71:72].strip() != ""
        # A continuation line resumes at column 16; columns 1-15 of it are the assembler's
        # name and operation fields and are not part of the operand.
        body = line[15:71] if joining else line[:71]
        out.append(body.rstrip())
        joining = continues
    return " ".join(part for part in out if part.strip())


def _values(value: str) -> List[str]:
    """``(A,B)`` -> ``[A, B]``; ``A`` -> ``[A]``. Empty parentheses give nothing."""
    v = value.strip()
    if v.startswith("(") and v.endswith(")"):
        v = v[1:-1]
    return [item.strip().strip("'") for item in v.split(",") if item.strip()]


def parse_sit(text: str, *, source_name: str = "<sit>",
              region: Optional[Region] = None) -> Region:
    """Read a SIT, an override deck or a DFHSIP PARM into ``region``.

    Later sources win, which is how CICS itself resolves them: the macro is the base, the
    override deck amends it, and PARM amends that.
    """
    region = region if region is not None else Region()
    region.sources.append(source_name)

    deck, wrapper_flags = macro_deck_source(text)
    region.flags.extend(wrapper_flags)
    joined = _join_assembler(deck)
    macro = _MACRO_NAME.search(joined)
    if macro:
        # The SIT's own spelling decides what its table suffixes name: FCT=DO under a
        # KIKSIT is the member KIKFCTDO, not DFHFCTDO.
        region.macro_prefix = macro.group(1)[:3].upper()
        joined = joined[macro.end():]

    found = 0
    for match in _KEYWORD.finditer(joined):
        keyword, value = match.group(1).upper(), match.group(2)
        if keyword == "TYPE":
            continue
        region.sit[keyword] = value.strip()
        found += 1

    if not found:
        region.flags.append(
            "%s: no SIT parameters were found in this source, so it decides nothing "
            "about what is installed" % source_name)
        return region

    if "APPLID" in region.sit:
        region.applid = _values(region.sit["APPLID"])[0]
    if "SYSIDNT" in region.sit:
        region.sysidnt = _values(region.sit["SYSIDNT"])[0]

    grplist = region.sit.get("GRPLIST")
    if grplist:
        for name in _values(grplist):
            if name not in region.grplist:
                region.grplist.append(name)
    else:
        region.flags.append(
            "%s: the SIT names no GRPLIST, so no CSD group can be shown as installed "
            "from it" % source_name)

    return region


def table_members(region: Region) -> List[Tuple[str, str, str]]:
    """``(parameter, member, why)`` for every table this SIT says is live.

    ``PLTPI=PI`` means the member ``DFHPLTPI``. These are what ``prefetch`` asks the estate
    for, and on a macro-era region they are also the answer to "which of these decks is
    actually loaded" - the question a stale deck in a PDS cannot answer for itself.
    """
    out: List[Tuple[str, str, str]] = []
    for parameter, stem in sorted(MEMBER_SUFFIX.items()):
        suffix = region.sit.get(parameter)
        if suffix is None:
            continue
        values = _values(suffix)
        if not values or values[0].upper() in _NO_TABLE:
            continue
        member = region.macro_prefix + stem[3:] + values[0]
        out.append((parameter, member,
                    "the SIT's %s=%s names this member" % (parameter, values[0])))
    return out
