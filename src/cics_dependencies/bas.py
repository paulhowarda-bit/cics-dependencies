"""CICSPlex SM Business Application Services -> the SAME Resource objects.

A ``BATCHREP`` (``EYU9XDBT``) deck: ``CREATE TRANDEF NAME(LGMN) PROGRAM(LGMENU)
RESGROUP(APPRG)``, and the ``RESGROUP``/``RESDESC`` structure that plays the part GROUP and
LIST play in a CSD.

The resource types are ``*DEF``-suffixed and a few attribute names differ, but **the edge
set is the same one in ``resources.ATTRIBUTES``** - a TRANDEF's ``PROGRAM`` is a
TRANSACTION's ``PROGRAM``. So this maps the type names and reuses the table, exactly as
``tables.py`` does for the macro era. Three syntaxes, one manifest shape.

The definitions themselves live in the CICSPlex SM data repository (``EYUDREP``), which is
not a parseable artifact. As with the CSD, what a site keeps in source control is the deck
that built it, and that is what this reads.

**A RESGROUP is not a CSD GROUP, and is not pretended to be one.** It is carried in
``Resource.group`` because it is the same idea - the unit a description installs - but the
install closure walks GRPLIST, and a BAS region is driven by a RESDESC instead. A BAS
resource therefore stays ``installed: unknown`` unless a CSD LIST happens to name a group
of the same name, and that is honest rather than convenient.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from .csd import build_references     # the same edges, read from the same table
from .lexer import BAS_COMMANDS, BAS_PAREN_COMMANDS, Statement, lex_csd
from .model import Region, Resource, SOURCE_BAS
from .resources import RESOURCE_TYPES

#: BAS object -> the CSD resource kind it defines. Only the objects whose CSD counterpart
#: this package models; anything else is named in a flag rather than dropped.
BAS_OBJECT = {
    "TRANDEF": "TRANSACTION", "PROGDEF": "PROGRAM", "FILEDEF": "FILE",
    "MAPDEF": "MAPSET", "TDQDEF": "TDQUEUE", "TSMDEF": "TSMODEL",
    "PROFDEF": "PROFILE", "TRNCLDEF": "TRANCLASS", "CONNDEF": "CONNECTION",
    "SESSDEF": "SESSIONS", "TERMDEF": "TERMINAL", "TYPTMDEF": "TYPETERM",
    "LSRDEF": "LSRPOOL", "JRNMDEF": "JOURNALMODEL", "DB2EDEF": "DB2ENTRY",
    "DB2TDEF": "DB2TRAN", "ENQMDEF": "ENQMODEL", "PROCDEF": "PROCESSTYPE",
}

#: The verbs that define something. CONTEXT and SCOPE set the target CICSplex and define
#: no resource; the rest change a repository this deck did not build.
_DEFINING = frozenset({"CREATE"})
_CONTEXTUAL = frozenset({"CONTEXT", "SCOPE"})


def _resource(stmt: Statement, obj: Optional[str], source_name: str) -> Optional[Resource]:
    if not obj:
        stmt.flags.append("line %d: CREATE with no object type defines nothing"
                          % stmt.line)
        return None
    kind = BAS_OBJECT.get(obj)
    if kind is None:
        stmt.flags.append(
            "line %d: CREATE %s is a CICSPlex SM object this package does not model; the "
            "definition was read but contributes no rows" % (stmt.line, obj))
        return None
    if kind not in RESOURCE_TYPES:
        return None

    attrs: Dict[str, str] = {}
    lines: Dict[str, int] = {}
    for op in stmt.operands:
        if op.keyword == obj:
            continue
        attrs[op.keyword] = "" if op.value is None else op.value
        lines[op.keyword] = op.line

    name = attrs.get("NAME")
    if not name:
        stmt.flags.append("line %d: CREATE %s has no NAME() and defines nothing"
                          % (stmt.line, obj))
        return None

    res = Resource(kind=kind, name=name.strip(), group=(attrs.get("RESGROUP") or None),
                   attributes=attrs, source=SOURCE_BAS, source_name=source_name,
                   line=stmt.line)
    res.references = build_references(kind, attrs, lines)
    if res.group is None:
        res.flags.append(
            "no RESGROUP - a BAS definition outside a resource group cannot be installed "
            "by any resource description")
    else:
        res.flags.append(
            "installed by a CICSPlex SM RESDESC, not by a CSD GRPLIST, so this "
            "package's install closure cannot decide it")
    return res


def parse_bas(text: str, *, source_name: str = "<bas>",
              region: Optional[Region] = None) -> Region:
    """Parse one BATCHREP deck into a Region, or add it to an existing one."""
    region = region if region is not None else Region()
    region.sources.append(source_name)

    statements, flags = lex_csd(text, BAS_COMMANDS, BAS_PAREN_COMMANDS)
    region.flags.extend(flags)

    created = 0
    for stmt in statements:
        if stmt.verb in _CONTEXTUAL:
            continue
        if stmt.verb not in _DEFINING:
            region.flags.append(
                "line %d: %s is not applied - it changes a CICSPlex SM repository this "
                "deck did not build, so what it operates on is not modelled here"
                % (stmt.line, stmt.verb))
            continue
        # `CREATE TRANDEF NAME(x)`: the object type is a bare operand, and the first one.
        obj = next((op.keyword for op in stmt.operands if op.value is None), None)
        res = _resource(stmt, obj, source_name)
        if res is not None:
            region.resources.append(res)
            created += 1
        region.flags.extend(stmt.flags)

    if not created:
        region.flags.append(
            "%s: no CREATE of a modelled CICSPlex SM object was found, so this source "
            "contributed nothing" % source_name)
    return region


__all__: List[str] = ["BAS_OBJECT", "parse_bas"]
