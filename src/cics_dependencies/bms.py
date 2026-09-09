"""BMS map source -> the one real field level CICS has.

``DFHMSD`` (mapset) / ``DFHMDI`` (map) / ``DFHMDF`` (field). Unlike every other CICS
artifact a map is **byte-addressable**: each field gives ``POS``, ``LENGTH``, ``ATTRB``,
``PICIN``/``PICOUT``, ``INITIAL`` and ``OCCURS``, so both ends of a lineage edge carry a
concrete position and length, the way an Easytrieve record layout does.

The join to application source is **mechanical, not conventional**. ``DFHMSD TYPE=DSECT``
generates a symbolic map in which a field ``CUSTNO`` becomes:

    CUSTNOL   halfword length / cursor
    CUSTNOF   flag byte (CUSTNOA in the input structure)
    CUSTNOA   attribute byte
    CUSTNOI   input value
    CUSTNOO   output value

So a screen position joins to the exact COBOL data names a program moves to and from, and a
program's ``terminal-map`` row resolves to a field list rather than only to a name. This is
the one place this package can say something about fields at all, and the reason it does
not claim more elsewhere: a COMMAREA layout is a convention, a container's contents are
not stated anywhere, and a TS queue record has no declaration.

**A mapset and a map are different things with one name.** ``DFHMSD LGMAP`` is the load
module the CSD's ``DEFINE MAPSET`` names; ``DFHMDI LGMENU`` is a map inside it, and no CSD
ever defines one. That is why ``bind_program_artifacts`` leaves a program's map row unbound
with a reason rather than calling it a missing definition - and why this module reports
both, kept apart.
"""

from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from typing import Dict, List, Optional

from .lexer import lex_macro
from .model import Region, Resource

#: The suffixes DFHMSD TYPE=DSECT appends to a field name, and what each carries. Emitted
#: per field so a consumer joining to COBOL data names does not have to know BMS.
SYMBOLIC_SUFFIXES = {
    "L": "halfword length, and the cursor position on input",
    "F": "flag byte - X'80' when the field was modified",
    "A": "attribute byte",
    "I": "the input value",
    "O": "the output value",
}


@dataclass
class MapField:
    """One ``DFHMDF``: a named position on a screen, with its length and picture."""

    name: Optional[str]
    pos: Optional[str] = None
    length: Optional[str] = None
    attrb: Optional[str] = None
    picin: Optional[str] = None
    picout: Optional[str] = None
    initial: Optional[str] = None
    occurs: Optional[str] = None
    line: int = 0

    def symbolic(self) -> List[dict]:
        """The COBOL data names this field generates in the symbolic map.

        Empty for an unnamed field: a ``DFHMDF`` with no label is a literal on the screen
        and generates nothing a program can reference. Reporting five data names for it
        would invent five COBOL fields that do not exist.
        """
        if not self.name:
            return []
        return [{"name": self.name + suffix, "carries": what}
                for suffix, what in sorted(SYMBOLIC_SUFFIXES.items())]


@dataclass
class Map:
    """One ``DFHMDI``: a screen within a mapset."""

    name: str
    size: Optional[str] = None
    line: int = 0
    fields: List[MapField] = dc_field(default_factory=list)


@dataclass
class Mapset:
    """One ``DFHMSD``: the load module a CSD ``DEFINE MAPSET`` names."""

    name: str
    mode: Optional[str] = None
    language: Optional[str] = None
    line: int = 0
    maps: List[Map] = dc_field(default_factory=list)
    source_name: str = "<bms>"
    flags: List[str] = dc_field(default_factory=list)


def _attrs(stmt) -> Dict[str, str]:
    return {op.keyword: (op.value or "") for op in stmt.operands}


def parse_bms(text: str, *, source_name: str = "<bms>") -> List[Mapset]:
    """Parse BMS macro source into mapsets, maps and fields.

    Returns mapsets rather than a Region: a mapset is not a CSD resource - the ``DEFINE
    MAPSET`` that names it is - and conflating the two would put a screen layout in the
    manifest as though the CSD had declared it.
    """
    mapsets: List[Mapset] = []
    current_set: Optional[Mapset] = None
    current_map: Optional[Map] = None
    orphan_fields = 0

    statements, flags = lex_macro(text)

    for stmt in statements:
        attrs = _attrs(stmt)
        if stmt.operation == "DFHMSD":
            if (attrs.get("TYPE") or "").upper() == "FINAL":
                current_set = current_map = None
                continue
            current_set = Mapset(name=stmt.label or "(unnamed)",
                                 mode=attrs.get("MODE"), language=attrs.get("LANG"),
                                 line=stmt.line, source_name=source_name)
            current_set.flags.extend(flags)
            flags = []
            mapsets.append(current_set)
            current_map = None
        elif stmt.operation == "DFHMDI":
            if current_set is None:
                current_set = Mapset(name="(no DFHMSD)", line=stmt.line,
                                     source_name=source_name)
                current_set.flags.append(
                    "a DFHMDI appeared before any DFHMSD, so this mapset has no name - "
                    "the CSD's DEFINE MAPSET cannot be joined to it")
                mapsets.append(current_set)
            current_map = Map(name=stmt.label or "(unnamed)", size=attrs.get("SIZE"),
                              line=stmt.line)
            current_set.maps.append(current_map)
        elif stmt.operation == "DFHMDF":
            if current_map is None:
                orphan_fields += 1
                continue
            current_map.fields.append(MapField(
                name=stmt.label, pos=attrs.get("POS"), length=attrs.get("LENGTH"),
                attrb=attrs.get("ATTRB"), picin=attrs.get("PICIN"),
                picout=attrs.get("PICOUT"), initial=attrs.get("INITIAL"),
                occurs=attrs.get("OCCURS"), line=stmt.line))

    if orphan_fields and mapsets:
        mapsets[-1].flags.append(
            "%d DFHMDF field(s) appeared outside any DFHMDI and were not placed - a field "
            "belongs to a map, and one with no map has no screen position" % orphan_fields)
    if not mapsets:
        return []
    mapsets[0].flags.extend(flags)
    return mapsets


def bind_mapsets(region: Region, mapsets: List[Mapset]) -> Region:
    """Attach parsed BMS detail to the ``DEFINE MAPSET`` resources that name it.

    A mapset with no matching definition is reported on the region: it is a real gap, since
    a mapset CICS cannot find is a mapset no transaction can send.
    """
    defined = {res.name: res for res in region.by_kind("MAPSET")}
    unmatched: List[str] = []
    for name in sorted({m.source_name for m in mapsets}):
        # The manifest's `sources` must name every file the run read. BMS does not produce
        # region resources, so without this a run that read a mapset reports sources it
        # did not have and omits one it did.
        if name not in region.sources:
            region.sources.append(name)
    for mapset in mapsets:
        res: Optional[Resource] = defined.get(mapset.name)
        if res is None:
            unmatched.append(mapset.name)
            continue
        res.attributes["_bmsSource"] = mapset.source_name
        res.flags.extend(mapset.flags)
    if unmatched:
        region.flags.append(
            "BMS source was supplied for %s, which no DEFINE MAPSET in these sources "
            "names. A mapset CICS cannot find is one no transaction can send"
            % ", ".join(sorted(unmatched)))
    return region


def build_bms_lineage(mapsets: List[Mapset]) -> dict:
    """The field view: every screen field, its position, and the COBOL names it generates.

    This is the one field-level lineage in the package, and it says so - everything else
    CICS names (COMMAREAs, containers, TS records) is named without a layout.
    """
    rows = []
    for mapset in mapsets:
        for mapping in mapset.maps:
            for fld in mapping.fields:
                rows.append({
                    "mapset": mapset.name,
                    "map": mapping.name,
                    "field": fld.name,
                    "pos": fld.pos,
                    "length": fld.length,
                    "attrb": fld.attrb,
                    "picin": fld.picin,
                    "picout": fld.picout,
                    "occurs": fld.occurs,
                    "initial": fld.initial,
                    "symbolic": fld.symbolic(),
                    "line": fld.line,
                })
    rows.sort(key=lambda r: (r["mapset"], r["map"], r["line"]))
    return {
        "format": "cics-dependencies-bms",
        "sources": sorted({m.source_name for m in mapsets}),
        "note": (
            "Every BMS field, with its screen position and the COBOL data names DFHMSD "
            "TYPE=DSECT generates from it - CUSTNO becomes CUSTNOL, CUSTNOF, CUSTNOA, "
            "CUSTNOI and CUSTNOO. This is the ONLY field-level lineage CICS definitions "
            "support: a COMMAREA's layout is a convention between two programs, a "
            "container's contents are stated nowhere, and a TS queue record has no "
            "declaration at all. An unnamed field is a screen literal and generates no "
            "data names, so its `symbolic` list is empty rather than guessed."),
        "mapsets": [{"mapset": m.name, "language": m.language, "mode": m.mode,
                     "maps": [{"map": x.name, "size": x.size, "fields": len(x.fields)}
                              for x in m.maps],
                     "flags": list(m.flags)}
                    for m in mapsets],
        "fields": rows,
    }
