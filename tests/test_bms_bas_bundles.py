"""BMS field lineage, CICSPlex SM BAS, and CICS bundles.

None of the three is validated against real source - no public corpus carries a BMS mapset
with its CSD, a BATCHREP deck, or a bundle manifest alongside the definitions they belong
to. The CSD path has AWS CardDemo behind it; these have the manuals.
"""

from pathlib import Path

from cics_dependencies.bas import parse_bas
from cics_dependencies.bms import bind_mapsets, build_bms_lineage, parse_bms
from cics_dependencies.bundles import bundle_directories, parse_bundle
from cics_dependencies.csd import parse_csd
from cics_dependencies.detect import (KIND_BAS, KIND_BMS, KIND_BUNDLE, KIND_CSD,
                                      KIND_MACRO, source_kind)
from cics_dependencies.model import SOURCE_BAS, SOURCE_BUNDLE

REPO = Path(__file__).resolve().parents[1]
BMS = (REPO / "examples" / "lgmap.bms").read_text(encoding="utf-8")
PCT = (REPO / "examples" / "legacy.pct").read_text(encoding="utf-8")
CSD = (REPO / "examples" / "appregn.csd").read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# detection
# --------------------------------------------------------------------------- #

def test_bms_and_macro_decks_are_told_apart_by_their_macros_not_their_suffix():
    """Both are assembler and both start with a label in column 1. Named by an estate
    service under whatever the library called them, the suffix says nothing."""
    assert source_kind(BMS) == KIND_BMS
    assert source_kind(PCT) == KIND_MACRO
    assert source_kind(CSD) == KIND_CSD


def test_a_bundle_manifest_and_a_bas_deck_are_recognised():
    assert source_kind('<?xml version="1.0"?><manifest/>') == KIND_BUNDLE
    assert source_kind("CREATE TRANDEF NAME(LGMN)\n") == KIND_BAS


# --------------------------------------------------------------------------- #
# BMS
# --------------------------------------------------------------------------- #

def test_a_mapset_holds_maps_and_maps_hold_fields():
    mapsets = parse_bms(BMS, source_name="lgmap.bms")
    assert [m.name for m in mapsets] == ["LGMAP"]
    assert [m.name for m in mapsets[0].maps] == ["LGMENU"]
    assert len(mapsets[0].maps[0].fields) == 5


def test_a_field_generates_the_five_symbolic_map_names():
    """The join to COBOL is mechanical, not conventional: CUSTNO becomes CUSTNOL,
    CUSTNOF, CUSTNOA, CUSTNOI, CUSTNOO."""
    view = build_bms_lineage(parse_bms(BMS, source_name="lgmap.bms"))
    custno = next(f for f in view["fields"] if f["field"] == "CUSTNO")
    assert {s["name"] for s in custno["symbolic"]} == {
        "CUSTNOL", "CUSTNOF", "CUSTNOA", "CUSTNOI", "CUSTNOO"}
    assert custno["pos"] == "(3,1)" and custno["length"] == "8"
    assert custno["picin"] == "'X(8)'"


def test_an_unnamed_field_generates_nothing():
    """A DFHMDF with no label is a screen literal. Five data names for it would invent
    five COBOL fields that do not exist."""
    mapsets = parse_bms(
        "LGMAP    DFHMSD TYPE=MAP,LANG=COBOL\n"
        "LGMENU   DFHMDI SIZE=(24,80)\n"
        "         DFHMDF POS=(1,1),LENGTH=10,INITIAL='HELLO'\n")
    assert mapsets[0].maps[0].fields[0].symbolic() == []


def test_a_mapset_joins_to_the_define_mapset_that_names_it():
    region = parse_csd(" DEFINE MAPSET(LGMAP) GROUP(G)\n")
    bind_mapsets(region, parse_bms(BMS, source_name="lgmap.bms"))
    assert region.by_kind("MAPSET")[0].attributes["_bmsSource"] == "lgmap.bms"
    assert "lgmap.bms" in region.sources


def test_a_mapset_no_definition_names_is_a_real_gap():
    """A mapset CICS cannot find is one no transaction can send."""
    region = parse_csd(" DEFINE TRANSACTION(T) GROUP(G) PROGRAM(P)\n")
    bind_mapsets(region, parse_bms(BMS, source_name="lgmap.bms"))
    assert any("no DEFINE MAPSET" in f for f in region.flags)


def test_the_bms_view_says_it_is_the_only_field_level_there_is():
    view = build_bms_lineage(parse_bms(BMS, source_name="lgmap.bms"))
    assert "COMMAREA" in view["note"] and "container" in view["note"]


# --------------------------------------------------------------------------- #
# BAS
# --------------------------------------------------------------------------- #

BAS_DECK = ("CONTEXT(EYUPLX01)\n"
            "CREATE TRANDEF NAME(LGMN) RESGROUP(APPRG)\n"
            "       PROGRAM(LGMENU) PROFILE(DFHCICST)\n"
            "CREATE PROGDEF NAME(LGMENU) RESGROUP(APPRG)\n"
            "CREATE WIDGETDEF NAME(SPROCKET) RESGROUP(APPRG)\n")


def test_a_trandef_produces_the_same_row_a_define_transaction_would():
    """Three syntaxes, one manifest shape - the whole reason resources.ATTRIBUTES is
    a table rather than parser behaviour."""
    region = parse_bas(BAS_DECK, source_name="bas.deck")
    txn = next(r for r in region.resources if r.kind == "TRANSACTION")
    assert txn.name == "LGMN" and txn.group == "APPRG"
    assert txn.source == SOURCE_BAS
    assert ("PROGRAM", "program", "LGMENU") in {
        (r.field, r.kind, r.name) for r in txn.references}


def test_context_defines_nothing_and_is_not_an_error():
    region = parse_bas(BAS_DECK, source_name="bas.deck")
    assert not any("CONTEXT" in f for f in region.flags)


def test_an_unmodelled_bas_object_is_named_rather_than_dropped():
    region = parse_bas(BAS_DECK, source_name="bas.deck")
    assert any("WIDGETDEF" in f for f in region.flags)


def test_bas_resources_say_the_install_closure_cannot_decide_them():
    """A RESGROUP is installed by a RESDESC, not by a CSD GRPLIST."""
    region = parse_bas(BAS_DECK, source_name="bas.deck")
    txn = next(r for r in region.resources if r.kind == "TRANSACTION")
    assert any("RESDESC" in f for f in txn.flags)


# --------------------------------------------------------------------------- #
# bundles
# --------------------------------------------------------------------------- #

MANIFEST = """<?xml version="1.0" encoding="UTF-8"?>
<manifest xmlns="http://www.ibm.com/xmlns/prod/cics/bundle">
  <define name="LGMN" type="http://www.ibm.com/xmlns/prod/cics/bundle/TRANSACTION"
          path="LGMN.transaction"/>
  <define name="LGMENU" type="http://www.ibm.com/xmlns/prod/cics/bundle/PROGRAM"
          path="LGMENU.program"/>
  <define name="POL1" type="http://www.ibm.com/xmlns/prod/cics/bundle/POLICY"
          path="POL1.policy"/>
</manifest>
"""

PARTS = {"LGMN.transaction": '<transaction name="LGMN" program="LGMENU"/>',
         "LGMENU.program": '<program name="LGMENU" language="cobol"/>'}


def test_the_resource_type_is_read_from_the_last_uri_segment():
    """Keyed on the whole namespace URI, a parser silently stops recognising anything the
    day a site upgrades CICS."""
    region = parse_bundle(MANIFEST, source_name="cics.xml", part=PARTS.get)
    assert {(r.kind, r.name) for r in region.resources} == {
        ("TRANSACTION", "LGMN"), ("PROGRAM", "LGMENU")}
    assert next(r for r in region.resources if r.name == "LGMN").source == SOURCE_BUNDLE


def test_a_bundle_part_supplies_the_attributes_and_therefore_the_edges():
    region = parse_bundle(MANIFEST, source_name="cics.xml", part=PARTS.get)
    txn = next(r for r in region.resources if r.name == "LGMN")
    assert ("PROGRAM", "program", "LGMENU") in {
        (r.field, r.kind, r.name) for r in txn.references}


def test_without_a_resolver_the_resource_exists_and_its_attributes_do_not():
    """A smaller and differently shaped gap from the resource being absent."""
    region = parse_bundle(MANIFEST, source_name="cics.xml")
    txn = next(r for r in region.resources if r.name == "LGMN")
    assert txn.references == []
    assert any("was not read" in f for f in txn.flags)


def test_an_unreadable_part_is_reported_with_its_path():
    region = parse_bundle(MANIFEST, source_name="cics.xml", part=lambda p: None)
    txn = next(r for r in region.resources if r.name == "LGMN")
    assert any("could not be read" in f and "LGMN.transaction" in f for f in txn.flags)


def test_an_unmodelled_bundle_type_is_counted_and_named():
    region = parse_bundle(MANIFEST, source_name="cics.xml", part=PARTS.get)
    assert any("POL1 (POLICY)" in f for f in region.flags)


def test_malformed_xml_is_not_an_empty_bundle():
    region = parse_bundle("<manifest", source_name="cics.xml")
    assert region.resources == []
    assert any("not the same as the bundle being empty" in f for f in region.flags)


def test_a_bundledir_nobody_read_is_listed_as_a_gap():
    region = parse_csd(" DEFINE BUNDLE(APPBUN) GROUP(G) BUNDLEDIR(/u/cics/appbun)\n")
    gaps = bundle_directories(region)
    assert gaps[0]["bundledir"] == "/u/cics/appbun"
    assert "second definition source" in gaps[0]["reason"]
