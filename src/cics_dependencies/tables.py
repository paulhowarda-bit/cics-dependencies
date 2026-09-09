"""Macro table decks -> the SAME Resource objects as csd.py.

``DFHPCT`` ``DFHPPT`` ``DFHFCT`` ``DFHDCT`` ``DFHTCT`` ``DFHTST`` ``DFHPLT`` ``DFHXLT``
``DSNCRCT``. ``resources.MACRO_RESOURCE`` maps each macro onto the CSD resource kind its
entries define and ``Attr.macro_field()`` gives the older spelling of each attribute, so a
1974 deck and a modern ``DEFINE`` produce an identical manifest row. Nothing about the edge
set is restated here.

Three era differences change the OUTPUT, not just the syntax:

**An FCT entry usually has no DSNAME.** The file-to-dataset binding is a DD on the CICS
region startup job, recoverable only through ``views.bind_jcl_region``. The row is emitted
unbound with a flag naming the region JCL; it is never omitted, because an omitted row is
indistinguishable from a file with nothing behind it.

**``DFHPPT`` is two resource kinds.** An entry carries either ``PROGRAM=`` or ``MAPSET=``,
so the kind is decided per entry rather than by the macro name.

**A macro deck has no groups.** There is no ``GROUP`` and no ``LIST`` - what makes a macro
table live is the SIT naming its suffix (``PCT=A1`` loads ``DFHPCTA1``). So these
resources cannot take part in the GRPLIST closure at all, and ``install.py`` reports them
``unknown`` unless the SIT names this deck.

**Not validated against real source, and this says so.** There is no public corpus of
macro table decks - they are 1970s-80s artifacts that survive only inside private estates -
so ``examples/legacy.pct`` is written from IBM's macro documentation and proves only that
this code does what it was built to do. The CSD path has AWS CardDemo behind it; this path
has nothing until a real deck arrives.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from .lexer import MacroStatement, lex_macro
from .model import (EVIDENCE_LITERAL, EVIDENCE_PREFIX, Reference, Region, Resource,
                    SOURCE_MACRO)
from .detect import macro_deck_source
from .resources import (MACRO_LISTS, MACRO_RESOURCE, NON_NAMES, attributes_for,
                        macro_family, permitted_io)

#: ``TYPE=`` values that define nothing: the table's own control sections and terminators.
_STRUCTURAL = frozenset({"INITIAL", "FINAL", "GROUP", "SDSCI"})

#: How each macro names the resource its entry defines. The CSD spells the name inside the
#: resource type's parentheses; a macro spells it in one of its operands, and which one
#: differs per macro.
_NAME_OPERAND = {
    "DFHPCT": ("TRANSID",),
    "DFHPPT": ("PROGRAM", "MAPSET"),
    "DFHFCT": ("DATASET", "FILE"),
    "DFHDCT": ("DESTID",),
    "DFHTST": ("DATAID", "PREFIX"),
    "DFHTCT": ("TRMIDNT",),
    "DSNCRCT": ("TXID",),
}


def _is_name(value: Optional[str]) -> bool:
    return value is not None and value.strip().strip("'").upper() not in NON_NAMES


def _clean(value: str) -> str:
    return value.strip().strip("'")


def _resource_kind(macro: str, attrs: Dict[str, str]) -> Optional[str]:
    """Which CSD resource kind this entry defines, or None if it defines nothing."""
    if macro == "DFHPPT":
        # Decided per ENTRY, not by the macro name: one deck defines both. And a mapset is
        # not always spelt MAPSET= - KICKS's own PPT writes
        # `TYPE=ENTRY,PROGRAM=KSGMAP,USAGE=MAP`, which is a mapset wearing PROGRAM=. Read
        # by the operand name alone, every one of its maps is reported as a program.
        if _is_name(attrs.get("MAPSET")):
            return "MAPSET"
        if _clean(attrs.get("USAGE", "")).upper() == "MAP":
            return "MAPSET"
        return "PROGRAM" if _is_name(attrs.get("PROGRAM")) else None
    return MACRO_RESOURCE.get(macro)


def _name_of(macro: str, kind: str, attrs: Dict[str, str]) -> Optional[str]:
    if macro == "DFHPPT":
        # Both kinds can be named by PROGRAM=; MAPSET= wins when it is there.
        for operand in ("MAPSET", "PROGRAM") if kind == "MAPSET" else ("PROGRAM",):
            if _is_name(attrs.get(operand)):
                return _clean(attrs[operand])
        return None
    for operand in _NAME_OPERAND.get(macro, ()):
        value = attrs.get(operand)
        if _is_name(value):
            return _clean(value)
    return None


def _references(kind: str, macro: str, attrs: Dict[str, str],
                lines: Dict[str, int]) -> List[Reference]:
    """The edges, read from the SAME table the CSD parser reads."""
    refs: List[Reference] = []
    io = permitted_io(attrs) if kind == "FILE" else None
    for attr in attributes_for(kind):
        if attr.relation == "self":
            continue
        field = attr.macro_field()
        value = attrs.get(field)
        if not _is_name(value):
            continue
        refs.append(Reference(
            field=field, name=_clean(value), kind=attr.kind, relation=attr.relation,
            evidence=EVIDENCE_PREFIX if attr.relation == "models" else EVIDENCE_LITERAL,
            io=io if attr.kind == "dataset" and kind == "FILE" else None,
            line=lines.get(field), note=attr.note))
    return refs


def _entry(stmt: MacroStatement, macro: str, source_name: str) -> Optional[Resource]:
    attrs: Dict[str, str] = {}
    lines: Dict[str, int] = {}
    for op in stmt.operands:
        attrs[op.keyword] = "" if op.value is None else op.value
        lines[op.keyword] = op.line

    entry_type = _clean(attrs.get("TYPE", "")).upper()
    if entry_type in _STRUCTURAL:
        return None

    if macro in MACRO_LISTS:
        operand, kind, relation = MACRO_LISTS[macro]
        value = attrs.get(operand)
        if not _is_name(value):
            return None
        res = Resource(kind=macro, name=_clean(value), source=SOURCE_MACRO,
                       source_name=source_name, line=stmt.line, attributes=attrs)
        res.references = [Reference(field=operand, name=_clean(value), kind=kind,
                                    relation=relation, evidence=EVIDENCE_LITERAL,
                                    line=lines.get(operand))]
        return res

    kind = _resource_kind(macro, attrs)
    if kind is None:
        return None
    name = _name_of(macro, kind, attrs)
    if name is None:
        return None

    res = Resource(kind=kind, name=name, group=None, attributes=attrs,
                   source=SOURCE_MACRO, source_name=source_name, line=stmt.line)
    res.references = _references(kind, macro, attrs, lines)
    res.flags.append(
        "defined in a macro table deck, which has no GROUP - what makes it live is the "
        "SIT naming this deck's suffix, not GRPLIST")
    if kind == "FILE" and not any(r.kind == "dataset" for r in res.references):
        res.flags.append(
            "this FCT entry carries no DSNAME, which is normal: the dataset is a DD on "
            "the CICS region startup job. Supply that job to bind_jcl_region to resolve "
            "it - until then this file has a name and nothing behind it")
    return res


def parse_tables(text: str, *, source_name: str = "<macro>",
                 region: Optional[Region] = None) -> Region:
    """Parse one macro table deck into a Region, or add it to an existing one."""
    region = region if region is not None else Region()
    region.sources.append(source_name)

    deck, wrapper_flags = macro_deck_source(text)
    region.flags.extend(wrapper_flags)
    statements, flags = lex_macro(deck)
    region.flags.extend(flags)

    seen_any = False
    aliased = set()
    for stmt in statements:
        # KICKS spells the same tables KIKPCT/KIKPPT/KIKFCT. Resolved to the IBM name so
        # one set of handlers serves both - and recorded, because "this deck is not IBM's"
        # is worth knowing when a row looks unfamiliar.
        macro = macro_family(stmt.operation)
        if macro is None:
            continue
        if macro != stmt.operation.upper():
            aliased.add("%s as %s" % (stmt.operation.upper(), macro))
        seen_any = True
        res = _entry(stmt, macro, source_name)
        if res is not None:
            region.resources.append(res)

    if aliased:
        region.flags.append(
            "%s uses non-IBM spellings of the table macros (%s) and was read as though "
            "they were IBM's. That holds while the OPERANDS match; a site macro with its "
            "own operand vocabulary would not be caught by this and is not modelled"
            % (source_name, ", ".join(sorted(aliased))))
    if not seen_any:
        region.flags.append(
            "%s: no CICS table macro (%s, or a site prefix of them) was found in this "
            "source, so it contributed nothing"
            % (source_name, ", ".join(sorted(set(MACRO_RESOURCE) | set(MACRO_LISTS)))))
    return region
