"""Statements -> Resources, and the edges that come out of resources.ATTRIBUTES."""

from cics_dependencies.csd import parse_csd, provides
from cics_dependencies.model import INSTALLED_UNKNOWN, SOURCE_CSD


def _refs(resource):
    return {(r.field, r.kind, r.name) for r in resource.references}


def _only(region, kind, name):
    return next(r for r in region.resources if r.kind == kind and r.name == name)


# --------------------------------------------------------------------------- #
# definitions
# --------------------------------------------------------------------------- #

def test_a_transaction_names_the_program_it_runs():
    region = parse_csd(" DEFINE TRANSACTION(CAUP) GROUP(CARDDEMO)\n"
                       "        PROGRAM(COACTUPC) PROFILE(DFHCICST)\n"
                       "        TRANCLASS(DFHTCL00) TWASIZE(0)\n")
    txn = _only(region, "TRANSACTION", "CAUP")
    assert txn.group == "CARDDEMO"
    assert txn.source == SOURCE_CSD
    assert ("PROGRAM", "program", "COACTUPC") in _refs(txn)
    assert ("PROFILE", "cics-profile", "DFHCICST") in _refs(txn)
    assert ("TRANCLASS", "cics-tranclass", "DFHTCL00") in _refs(txn)
    # TWASIZE names no artifact and must not become one.
    assert not any(r.field == "TWASIZE" for r in txn.references)
    # ...but it is still carried, because it is often why someone opened the manifest.
    assert txn.attributes["TWASIZE"] == "0"


def test_a_file_binds_the_dataset_and_reports_permitted_access():
    region = parse_csd(" DEFINE FILE(ACCTDAT) GROUP(CARDDEMO)\n"
                       "        DSNAME(AWS.M2.ACCTDATA.KSDS)\n"
                       "        READ(YES) BROWSE(YES) ADD(YES)\n"
                       "        UPDATE(YES) DELETE(YES)\n")
    row = next(r for r in _only(region, "FILE", "ACCTDAT").references
               if r.kind == "dataset")
    assert row.name == "AWS.M2.ACCTDATA.KSDS"
    assert row.io == "read-write"


def test_a_read_only_file_says_read():
    region = parse_csd(" DEFINE FILE(USRSEC) GROUP(G) DSNAME(A.B.C)\n"
                       "        READ(YES) BROWSE(YES)\n"
                       "        ADD(NO) UPDATE(NO) DELETE(NO)\n")
    row = next(r for r in _only(region, "FILE", "USRSEC").references
               if r.kind == "dataset")
    assert row.io == "read"


def test_no_and_none_never_become_artifacts():
    """JOURNAL(NO) and REMOTESYSTEM(NONE) are switches. An edge built from either is an
    artifact literally named NO, which joins to nothing and reads as a real dependency."""
    region = parse_csd(" DEFINE FILE(X) GROUP(G) DSNAME(A.B)\n"
                       "        JOURNAL(NO) REMOTESYSTEM(NONE)\n")
    kinds = {r.kind for r in _only(region, "FILE", "X").references}
    assert kinds == {"dataset"}


def test_a_library_keeps_its_slots_in_search_order():
    region = parse_csd(" DEFINE LIBRARY(CARDDLIB) GROUP(G) RANKING(50)\n"
                       "        DSNAME01(A.LOADLIB) DSNAME02(B.LOADLIB)\n")
    refs = _only(region, "LIBRARY", "CARDDLIB").references
    assert [(r.field, r.name) for r in refs] == [
        ("DSNAME01", "A.LOADLIB"), ("DSNAME02", "B.LOADLIB")]
    assert "slot 1" in refs[0].note and "slot 2" in refs[1].note


def test_a_td_queue_write_triggers_a_transaction():
    """The edge people miss: a write to this queue starts a task, and the write can come
    from a batch job through the extrapartition dataset."""
    region = parse_csd(" DEFINE TDQUEUE(ORDQ) GROUP(G) TYPE(INTRA)\n"
                       "        TRANSID(ORD1) TRIGGERLEVEL(1)\n")
    ref = next(r for r in _only(region, "TDQUEUE", "ORDQ").references
               if r.kind == "cics-transaction")
    assert (ref.name, ref.relation) == ("ORD1", "triggers")


def test_a_tsmodel_matches_by_prefix_and_says_so():
    region = parse_csd(" DEFINE TSMODEL(CUSTWRK) GROUP(G) PREFIX(CUSTWRK)\n")
    ref = _only(region, "TSMODEL", "CUSTWRK").references[0]
    assert ref.relation == "models"
    assert ref.evidence == "prefix"


# --------------------------------------------------------------------------- #
# groups, lists and the honest gaps
# --------------------------------------------------------------------------- #

def test_add_records_the_group_to_list_membership_both_ways():
    region = parse_csd(" DEFINE FILE(X) GROUP(APPG)\n"
                       " ADD GROUP(APPG) LIST(APPLIST)\n")
    assert region.lists["APPLIST"].groups == ["APPG"]
    assert region.groups["APPG"].lists == ["APPLIST"]


def test_everything_starts_unknown_until_a_sit_arrives():
    region = parse_csd(" DEFINE TRANSACTION(CAUP) GROUP(G) PROGRAM(P)\n")
    assert all(r.installed == INSTALLED_UNKNOWN for r in region.resources)


def test_a_definition_with_no_group_cannot_be_installed_and_says_so():
    region = parse_csd(" DEFINE TRANSACTION(CAUP) PROGRAM(COACTUPC)\n")
    assert any("cannot be installed" in f
               for f in _only(region, "TRANSACTION", "CAUP").flags)


def test_restructuring_commands_are_flagged_rather_than_applied():
    """COPY, APPEND, REMOVE and DELETE change what a later DEFINE means. A deck replayed
    without them models a CSD that never existed."""
    region = parse_csd(" REMOVE Group(G) List(L)\n"
                       " DELETE Group(G) All\n"
                       " DEFINE FILE(X) GROUP(G)\n")
    assert sum("is not applied" in f for f in region.flags) == 2
    assert len(region.resources) == 1


def test_an_unknown_resource_type_is_named_not_dropped():
    region = parse_csd(" DEFINE WIDGET(SPROCKET) GROUP(G)\n")
    assert region.resources == []
    assert any("WIDGET" in f for f in region.flags)


def test_a_duplicated_attribute_is_reported():
    region = parse_csd(" DEFINE TRANSACTION(T) GROUP(G)\n"
                       "        PROGRAM(FIRST) PROGRAM(SECOND)\n")
    txn = _only(region, "TRANSACTION", "T")
    assert any("given twice" in f for f in txn.flags)
    assert ("PROGRAM", "program", "SECOND") in _refs(txn)


# --------------------------------------------------------------------------- #
# provides
# --------------------------------------------------------------------------- #

def test_provides_is_the_index_a_peer_manifest_joins_to():
    region = parse_csd(" DEFINE TRANSACTION(CAUP) GROUP(G) PROGRAM(COACTUPC)\n"
                       " DEFINE MAPSET(COACTUP) GROUP(G)\n"
                       " DEFINE FILE(ACCTDAT) GROUP(G) DSNAME(A.B)\n",
                       source_name="CARDDEMO.CSD")
    rows = {(r["kind"], r["name"]) for r in provides(region)}
    assert rows == {("cics-transaction", "CAUP"), ("terminal-map", "COACTUP"),
                    ("file", "ACCTDAT")}


def test_several_decks_assemble_into_one_region():
    region = parse_csd(" DEFINE FILE(X) GROUP(A)\n", source_name="one.csd")
    region = parse_csd(" DEFINE FILE(Y) GROUP(B)\n", source_name="two.csd",
                       region=region)
    assert region.sources == ["one.csd", "two.csd"]
    assert len(region.resources) == 2
