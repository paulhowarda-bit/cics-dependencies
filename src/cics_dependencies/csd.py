"""DFHCSDUP statements -> Resource / GroupDef / ListDef, assembled into a Region.

``DEFINE`` and ``ADD`` are modelled. The restructuring commands (``COPY``, ``APPEND``,
``REMOVE``, ``DELETE``) are recognised and FLAGGED rather than applied: they change what a
later ``DEFINE`` means, and a deck replayed without them models a CSD that never existed.
Flagging says so; skipping them silently would not.

Every edge comes from ``resources.ATTRIBUTES``. This module never decides that an
attribute names an artifact - it looks the attribute up, and an attribute missing from the
table simply produces no edge. That is the point of keeping the table separate, and it is
why adding a resource type here without adding its attributes there is the one change that
loses dependencies without any output saying so.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from .detect import csd_source
from .lexer import Statement, lex_csd
from .model import (
    EVIDENCE_LITERAL, EVIDENCE_PREFIX, GroupDef, ListDef, Reference, Region, Resource,
    SOURCE_CSD,
)
from .resources import (
    NON_NAMES, PROVIDES_KIND, RESOURCE_TYPES, attributes_for, permitted_io,
)

#: Commands that restructure the CSD rather than define anything in it.
_RESTRUCTURING = {
    "COPY":   "copies definitions between groups, so a later DEFINE in this deck may be "
              "operating on a group whose contents this model does not have",
    "APPEND": "appends one list to another, changing which groups a GRPLIST reaches",
    "REMOVE": "removes a group from a list, so a group modelled as installed may not be",
    "DELETE": "deletes definitions, so a resource modelled here may no longer exist",
    "ALTER":  "alters attributes of an existing definition, which this model does not "
              "hold unless the DEFINE is also in this deck",
}

#: Commands that name no resource and change nothing.
_INERT = frozenset({"LIST", "EXTRACT", "INITIALIZE", "UPGRADE", "SCAN", "SERVICE",
                    "VERIFY", "MIGRATE", "PROCESS"})

#: LIBRARY spells its concatenation ``DSNAME01``..``DSNAME16``. The SLOT ORDER is the
#: load-module search order, so the rows are emitted in it and the slot is kept on each.
_LIBRARY_SLOTS = tuple("DSNAME%02d" % n for n in range(1, 17))


def _is_name(value: Optional[str]) -> bool:
    return value is not None and value.strip().upper() not in NON_NAMES


def build_references(kind: str, attrs: Dict[str, str],
                     lines: Dict[str, int]) -> List[Reference]:
    """The edges this definition writes, looked up in the table rather than decided here.

    Public because ``bas.py`` needs exactly this: a BAS ``TRANDEF``'s attributes are a
    TRANSACTION's attributes, so the two eras must produce identical rows or the point of
    keeping one table is lost.
    """
    refs: List[Reference] = []
    io = permitted_io(attrs) if kind == "FILE" else None

    for attr in attributes_for(kind):
        if attr.relation == "self":
            continue
        # LIBRARY's DSNAME is really sixteen numbered slots.
        if kind == "LIBRARY" and attr.field == "DSNAME":
            for slot, field in enumerate(_LIBRARY_SLOTS, start=1):
                value = attrs.get(field)
                if _is_name(value):
                    refs.append(Reference(
                        field=field, name=value.strip(), kind=attr.kind,
                        relation=attr.relation, evidence=EVIDENCE_LITERAL,
                        line=lines.get(field), note="search order slot %d" % slot))
            continue
        value = attrs.get(attr.field)
        if not _is_name(value):
            continue
        refs.append(Reference(
            field=attr.field, name=value.strip(), kind=attr.kind,
            relation=attr.relation,
            evidence=EVIDENCE_PREFIX if attr.relation == "models" else EVIDENCE_LITERAL,
            io=io if attr.kind == "dataset" and kind == "FILE" else None,
            line=lines.get(attr.field), note=attr.note))
    return refs


def _define(stmt: Statement, source_name: str) -> Optional[Resource]:
    """``DEFINE <type>(name) GROUP(g) <attrs>`` -> one Resource, or None with a flag."""
    if not stmt.operands:
        stmt.flags.append("line %d: DEFINE with no resource type" % stmt.line)
        return None

    first = stmt.operands[0]
    rtype = first.keyword
    if rtype not in RESOURCE_TYPES:
        stmt.flags.append(
            "line %d: DEFINE %s is not a CICS resource type this package knows; the "
            "definition was read but contributes no rows" % (stmt.line, rtype))
        return None
    if not first.value:
        stmt.flags.append("line %d: DEFINE %s names nothing" % (stmt.line, rtype))
        return None

    attrs: Dict[str, str] = {}
    lines: Dict[str, int] = {}
    duplicates: List[str] = []
    for op in stmt.operands[1:]:
        value = "" if op.value is None else op.value
        if op.keyword in attrs and attrs[op.keyword] != value:
            duplicates.append(op.keyword)
        attrs[op.keyword] = value
        lines[op.keyword] = op.line

    res = Resource(
        kind=rtype, name=first.value.strip(), group=(attrs.get("GROUP") or None),
        attributes=attrs, source=SOURCE_CSD, source_name=source_name, line=stmt.line,
    )
    for keyword in duplicates:
        res.flags.append(
            "%s is given twice with different values; the last was kept" % keyword)
    if res.group is None:
        res.flags.append(
            "no GROUP - a definition outside a group cannot be installed by any LIST")
    res.references = build_references(rtype, attrs, lines)
    return res


def parse_csd(text: str, *, source_name: str = "<csd>",
              region: Optional[Region] = None) -> Region:
    """Parse one DFHCSDUP deck into a Region, or add it to an existing one.

    Several decks routinely make up one region, which is why ``region`` is threaded rather
    than a new one always returned. ``install.py`` decides what is live once a SIT arrives;
    until then every resource keeps ``installed = unknown``.
    """
    region = region if region is not None else Region()
    region.sources.append(source_name)

    deck, wrapper_flags = csd_source(text)
    region.flags.extend(wrapper_flags)
    statements, flags = lex_csd(deck)
    region.flags.extend(flags)

    for stmt in statements:
        if stmt.verb == "DEFINE" or stmt.verb == "USERDEFINE":
            res = _define(stmt, source_name)
            if res is not None:
                region.resources.append(res)
                if res.group:
                    region.groups.setdefault(res.group,
                                             GroupDef(res.group, source_name=source_name))
        elif stmt.verb == "ADD":
            group = stmt.first("GROUP")
            listname = stmt.first("LIST")
            if not group or not listname:
                stmt.flags.append(
                    "line %d: ADD without both GROUP and LIST names no membership"
                    % stmt.line)
            else:
                lst = region.lists.setdefault(
                    listname, ListDef(listname, source_name=source_name))
                if group not in lst.groups:
                    lst.groups.append(group)
                grp = region.groups.setdefault(
                    group, GroupDef(group, source_name=source_name))
                if listname not in grp.lists:
                    grp.lists.append(listname)
        elif stmt.verb in _RESTRUCTURING:
            region.flags.append(
                "line %d: %s is not applied - it %s"
                % (stmt.line, stmt.verb, _RESTRUCTURING[stmt.verb]))
        elif stmt.verb not in _INERT:
            region.flags.append("line %d: unrecognised command %s"
                                % (stmt.line, stmt.verb))
        region.flags.extend(stmt.flags)

    return region


def provides(region: Region) -> List[dict]:
    """Every resource this region DEFINES, as the index a peer's manifest joins to.

    Sorted by (kind, name) so the output is stable, and carrying the group and the source
    era, because when two eras define one resource both rows are here and the reader has
    to be able to tell them apart.
    """
    rows = [{"name": r.name, "kind": PROVIDES_KIND.get(r.kind, r.kind.lower()),
             "resourceType": r.kind, "group": r.group, "source": r.source,
             "sourceName": r.source_name, "line": r.line, "installed": r.installed}
            for r in region.resources]
    rows.sort(key=lambda row: (row["kind"], row["name"], row["sourceName"], row["line"]))
    return rows
