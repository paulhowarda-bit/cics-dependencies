"""The macro table era.

NOT validated against real source. There is no public corpus of DFHPCT/DFHFCT decks, so
``examples/legacy.pct`` is written from IBM's macro documentation and proves only that this
code does what it was built to do - unlike the CSD path, which has AWS CardDemo behind it.
The assembler lexer under it moved to cics-parser (mainframe-common), and its tests with it.
"""

from pathlib import Path

from cics_dependencies.model import SOURCE_MACRO
from cics_dependencies.tables import parse_tables

REPO = Path(__file__).resolve().parents[1]
DECK = (REPO / "examples" / "legacy.pct").read_text(encoding="utf-8")


def _only(region, kind, name):
    return next(r for r in region.resources if r.kind == kind and r.name == name)


# --------------------------------------------------------------------------- #
# the decks
# --------------------------------------------------------------------------- #

def test_the_deck_yields_the_same_resource_kinds_a_csd_would():
    region = parse_tables(DECK, source_name="legacy.pct")
    kinds = {}
    for res in region.resources:
        kinds[res.kind] = kinds.get(res.kind, 0) + 1
    assert kinds == {"TRANSACTION": 2, "PROGRAM": 2, "MAPSET": 1, "FILE": 2,
                     "TDQUEUE": 2, "DB2ENTRY": 1}


def test_a_pct_entry_produces_the_same_row_a_define_transaction_would():
    region = parse_tables(DECK, source_name="legacy.pct")
    txn = _only(region, "TRANSACTION", "LGMN")
    assert txn.source == SOURCE_MACRO
    assert ("PROGRAM", "program", "LGMENU") in {
        (r.field, r.kind, r.name) for r in txn.references}


def test_dfhppt_is_two_kinds_decided_per_entry():
    region = parse_tables(DECK, source_name="legacy.pct")
    assert _only(region, "MAPSET", "LGMAP").kind == "MAPSET"
    assert _only(region, "PROGRAM", "LGMENU").kind == "PROGRAM"


def test_structural_entries_define_nothing():
    """TYPE=INITIAL and TYPE=FINAL are the table's own control sections."""
    region = parse_tables(
        "DFHPCTL1 DFHPCT TYPE=INITIAL,SUFFIX=L1\n"
        "         DFHPCT TYPE=FINAL\n")
    assert region.resources == []


def test_an_fct_entry_has_no_dataset_and_says_where_one_would_come_from():
    """The era difference that changes output rather than syntax."""
    region = parse_tables(DECK, source_name="legacy.pct")
    fct = _only(region, "FILE", "CUSTMAS")
    assert not any(r.kind == "dataset" for r in fct.references)
    assert any("no DSNAME" in f and "startup job" in f for f in fct.flags)


def test_servreq_is_the_macro_spelling_of_the_csd_switches():
    from cics_dependencies.resources import permitted_io
    region = parse_tables(DECK, source_name="legacy.pct")
    assert permitted_io(_only(region, "FILE", "CUSTMAS").attributes) == "read-write"
    assert permitted_io(_only(region, "FILE", "RATETAB").attributes) == "read"


def test_a_dct_dscname_is_a_ddname_not_a_dataset():
    """Same rule as the CSD's DDNAME: what DSCNAME points at is on the region startup job,
    so it is a `file` awaiting a dataset, never a catalogued dataset of that name."""
    region = parse_tables(DECK, source_name="legacy.pct")
    rptq = _only(region, "TDQUEUE", "RPTQ")
    assert [(r.field, r.kind, r.name) for r in rptq.references] == [
        ("DSCNAME", "file", "LGRPT")]


def test_a_queue_trigger_survives_the_era_change():
    region = parse_tables(DECK, source_name="legacy.pct")
    ordq = _only(region, "TDQUEUE", "ORDQ")
    ref = next(r for r in ordq.references if r.kind == "cics-transaction")
    assert (ref.name, ref.relation) == ("LGOR", "triggers")


def test_the_rct_binds_a_transaction_to_a_db2_plan():
    region = parse_tables(DECK, source_name="legacy.pct")
    entry = _only(region, "DB2ENTRY", "LGOR")
    assert ("PLAN", "db2-plan", "LGPLAN") in {
        (r.field, r.kind, r.name) for r in entry.references}


def test_every_macro_resource_says_it_has_no_group():
    """A macro table has no GROUP and no LIST, so it cannot take part in the GRPLIST
    closure at all. Left unsaid, its resources would read as an un-installed application."""
    region = parse_tables(DECK, source_name="legacy.pct")
    assert all(any("no GROUP" in f for f in res.flags) for res in region.resources)


def test_a_source_with_no_table_macros_says_it_contributed_nothing():
    region = parse_tables("         WTO   'HELLO'\n         END\n", source_name="x.asm")
    assert region.resources == []
    assert any("contributed nothing" in f for f in region.flags)
