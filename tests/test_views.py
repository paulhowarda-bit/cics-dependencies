"""The manifest view."""

from cics_dependencies.csd import parse_csd
from cics_dependencies.install import apply_install_state
from cics_dependencies.sit import parse_sit
from cics_dependencies.views import (FORMAT_ARTIFACTS, build_cics_artifacts,
                                     build_cics_lineage)

DECK = (" DEFINE TRANSACTION(CAUP) GROUP(APPG)\n"
        "        PROGRAM(COACTUPC) PROFILE(DFHCICST) TRANCLASS(DFHTCL00)\n"
        " DEFINE FILE(ACCTDAT) GROUP(APPG) DSNAME(AWS.M2.ACCTDATA)\n"
        "        READ(YES) UPDATE(YES)\n"
        " ADD GROUP(APPG) LIST(APPLIST)\n")


def _row(manifest, name):
    return next(r for r in manifest["artifacts"] if r["artifact"] == name)


def _excluded(manifest, name):
    return next(r for r in manifest["excluded"] if r["name"] == name)


def test_the_subject_key_is_region():
    """mainframe_artifacts.fetch reads program/job/region to know what NOT to fetch.
    Keyed anything else the guard holds '?' and the region asks the estate for itself."""
    manifest = build_cics_artifacts(parse_csd(DECK, source_name="APP.CSD"))
    assert manifest["region"] == "APP.CSD"
    assert manifest["format"] == FORMAT_ARTIFACTS


def test_the_applid_is_the_region_name_once_a_sit_says_so():
    region = parse_csd(DECK, source_name="APP.CSD")
    parse_sit(" DFHSIT TYPE=CSECT,APPLID=CICSPRDA,GRPLIST=(APPLIST)\n", region=region)
    assert build_cics_artifacts(region)["region"] == "CICSPRDA"


def test_a_transaction_yields_a_program_row_naming_its_source_line():
    manifest = build_cics_artifacts(parse_csd(DECK))
    row = _row(manifest, "COACTUPC")
    assert row["kind"] == "program"
    assert row["relation"] == "runs"
    assert row["evidence"] == "literal"
    assert row["touchedBy"] == [{"resource": "CAUP", "resourceType": "TRANSACTION",
                                 "group": "APPG", "field": "PROGRAM",
                                 "relation": "runs", "line": 2}]


def test_a_file_row_says_its_io_is_permitted_not_observed():
    row = _row(build_cics_artifacts(parse_csd(DECK)), "AWS.M2.ACCTDATA")
    assert row["io"] == "read-write"
    assert "not observed" in row["ioMeaning"]


def test_ibm_supplied_names_are_excluded_with_a_reason():
    """Every transaction in a real CSD names DFHCICST and DFHTCL00. Left in, they are
    rows the estate can only answer 'not found' to, and they bury the real ones."""
    manifest = build_cics_artifacts(parse_csd(DECK))
    assert {r["artifact"] for r in manifest["artifacts"]} == {"COACTUPC",
                                                              "AWS.M2.ACCTDATA"}
    assert _excluded(manifest, "DFHCICST")["category"] == "ibm-runtime"
    assert _excluded(manifest, "DFHTCL00")["category"] == "ibm-runtime"


def test_an_unregistered_kind_is_excluded_saying_what_is_missing_upstream():
    manifest = build_cics_artifacts(parse_csd(
        " DEFINE FILE(X) GROUP(G) DSNAME(A.B) LSRPOOLNUM(1)\n"))
    row = _excluded(manifest, "1")
    assert row["category"] == "not-retrievable-yet"
    assert "_KIND_TYPE" in row["reason"]


def test_a_resource_defined_in_these_sources_says_where():
    """A transaction named by a PROGRAM's TRANSID is usually defined in the same deck.
    Without this, stage 2 goes to the estate for something already in hand."""
    manifest = build_cics_artifacts(parse_csd(
        " DEFINE PROGRAM(COACTVWC) GROUP(G) TRANSID(CAVW)\n"
        " DEFINE TRANSACTION(CAVW) GROUP(G) PROGRAM(COACTVWC)\n", source_name="a.csd"))
    assert _row(manifest, "CAVW")["definedIn"]["source"] == "a.csd"
    assert _row(manifest, "CAVW")["definedIn"]["line"] == 2


def test_installed_state_rides_on_every_row():
    region = parse_csd(DECK)
    parse_sit(" DFHSIT TYPE=CSECT,GRPLIST=(APPLIST)\n", region=region)
    apply_install_state(region)
    manifest = build_cics_artifacts(region)
    assert _row(manifest, "COACTUPC")["installed"] == "installed"
    assert all(p["installed"] == "installed" for p in manifest["provides"])


def test_two_definitions_of_one_resource_are_both_kept_and_flagged():
    """The two-eras rule. Neither wins - a stale deck reads exactly like a current one."""
    region = parse_csd(" DEFINE TRANSACTION(MENU) GROUP(A) PROGRAM(MENU001)\n",
                       source_name="old.csd")
    region = parse_csd(" DEFINE TRANSACTION(MENU) GROUP(B) PROGRAM(MENU009)\n",
                       source_name="new.csd", region=region)
    manifest = build_cics_artifacts(region)
    assert {r["artifact"] for r in manifest["artifacts"]} == {"MENU001", "MENU009"}
    assert len([p for p in manifest["provides"] if p["name"] == "MENU"]) == 2
    conflict = next(f for f in manifest["flags"] if "defined 2 times" in f)
    assert "old.csd" in conflict and "new.csd" in conflict
    assert "neither definition is preferred" in conflict


def test_provides_and_artifacts_are_the_two_directions():
    manifest = build_cics_artifacts(parse_csd(DECK))
    assert {(p["kind"], p["name"]) for p in manifest["provides"]} == {
        ("cics-transaction", "CAUP"), ("file", "ACCTDAT")}
    assert {(a["kind"], a["artifact"]) for a in manifest["artifacts"]} == {
        ("program", "COACTUPC"), ("dataset", "AWS.M2.ACCTDATA")}


def test_the_whole_manifest_is_json_serialisable():
    import json
    region = parse_csd(DECK)
    parse_sit(" DFHSIT TYPE=CSECT,APPLID=CICSA,GRPLIST=(APPLIST)\n", region=region)
    apply_install_state(region)
    json.dumps(build_cics_artifacts(region))


# --------------------------------------------------------------------------- #
# lineage
# --------------------------------------------------------------------------- #

WIRED = (" DEFINE TRANSACTION(APMN) GROUP(APPG) PROGRAM(APPMENU)\n"
         " DEFINE TRANSACTION(APOR) GROUP(APPG) PROGRAM(APPORDR)\n"
         " DEFINE TERMINAL(TRM1) GROUP(APPG) TYPETERM(DFHLU2)\n"
         "        TRANSACTION(APMN)\n"
         " DEFINE TDQUEUE(ORDQ) GROUP(APPG) TYPE(INTRA)\n"
         "        TRANSID(APOR) TRIGGERLEVEL(1)\n"
         " DEFINE URIMAP(APPWEB) GROUP(APPG) TRANSACTION(APOR)\n")


def _txn(lineage, name):
    return next(t for t in lineage["transactions"] if t["transaction"] == name)


def test_entry_points_come_from_the_relation_not_a_list_of_types():
    lineage = build_cics_lineage(parse_csd(WIRED))
    assert {(e["transaction"], e["kind"], e["via"]) for e in lineage["entryPoints"]} == {
        ("APMN", "TERMINAL", "starts"),
        ("APOR", "TDQUEUE", "triggers"),
        ("APOR", "URIMAP", "starts")}


def test_started_by_is_the_reverse_index():
    """The direction a definition does not read in: not what this transaction needs, but
    what reaches it."""
    lineage = build_cics_lineage(parse_csd(WIRED))
    assert [e["name"] for e in _txn(lineage, "APOR")["startedBy"]] == ["ORDQ", "APPWEB"]
    assert _txn(lineage, "APOR")["runs"] == "APPORDR"


def test_the_sit_good_morning_transaction_is_an_entry_point():
    region = parse_csd(WIRED)
    parse_sit(" DFHSIT TYPE=CSECT,GMTRAN=APMN,GRPLIST=(APPLIST)\n", region=region)
    lineage = build_cics_lineage(region)
    gm = next(e for e in lineage["entryPoints"] if e["kind"] == "SIT")
    assert gm["transaction"] == "APMN"
    # The SIT installs everything else, so an entry point it states is live by definition.
    assert gm["installed"] == "installed"


def test_a_routed_transaction_runs_nothing_here():
    lineage = build_cics_lineage(parse_csd(
        " DEFINE TRANSACTION(APRM) GROUP(G) REMOTESYSTEM(CICSBK1)\n"))
    assert _txn(lineage, "APRM")["runs"] is None
    assert _txn(lineage, "APRM")["routedTo"] == "CICSBK1"


def test_unreachable_is_stated_as_normal_and_not_as_dead_code():
    """The commonest entry point in any region - a user typing four characters - is
    recorded nowhere. A view that let 'nothing starts this' read as 'nothing runs this'
    would retire live transactions."""
    lineage = build_cics_lineage(parse_csd(
        " DEFINE TRANSACTION(APMN) GROUP(G) PROGRAM(APPMENU)\n"))
    assert lineage["unreachable"] == ["APMN"]
    flag = next(f for f in lineage["flags"] if "started by nothing" in f)
    assert "not evidence they are dead" in flag
    assert any("typing a four-character transaction id" in b
               for b in lineage["boundary"])


def test_the_boundary_names_the_program_side_gap():
    lineage = build_cics_lineage(parse_csd(WIRED))
    assert any("EXEC CICS START" in b for b in lineage["boundary"])
    assert any("bind_program_artifacts" in b for b in lineage["boundary"])
