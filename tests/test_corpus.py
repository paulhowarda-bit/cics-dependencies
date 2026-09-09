"""The public corpus: real CICS decks, not fixtures written for this repository.

Examples written here only prove the tool does what it was built to do. These two files
are real - and between them they have already found four defects that no synthetic
fixture in this suite would have produced: values containing blanks and commas, a
DESCRIPTION in the same column as DEFINE, mixed-case commands, and a deck arriving inside
a whole JCL job rather than as a file of DEFINEs.

The corpus is not committed (third-party, Apache 2.0). `python tools/fetch_corpus.py`
downloads it; without it these skip.
"""

from pathlib import Path

import pytest

from cics_dependencies.bms import build_bms_lineage, parse_bms
from cics_dependencies.csd import parse_csd, provides
from cics_dependencies.detect import (KIND_MACRO, KIND_SIT, source_kind)
from cics_dependencies.install import apply_install_state
from cics_dependencies.sit import parse_sit, table_members
from cics_dependencies.tables import parse_tables
from cics_dependencies.views import build_cics_artifacts, build_cics_lineage

CORPUS = Path(__file__).resolve().parents[1] / "corpus"


def _text(name):
    path = CORPUS / name
    if not path.is_file():
        pytest.skip("corpus absent - run `python tools/fetch_corpus.py` to fetch %s"
                    % name)
    return path.read_text(encoding="utf-8", errors="replace")


def _load(name):
    return parse_csd(_text(name), source_name=name)


@pytest.fixture(scope="module")
def carddemo():
    return _load("CARDDEMO.CSD")


@pytest.fixture(scope="module")
def hcaz():
    return _load("HCAZ.CSDUP.JCL")


# --------------------------------------------------------------------------- #
# AWS CardDemo - a DFHCSDUP EXTRACT-shaped deck, bare
# --------------------------------------------------------------------------- #

def test_carddemo_parses_completely_and_cleanly(carddemo):
    """64 DEFINEs, no flags. A flag appearing here is either a real defect or a real
    finding about the deck, and either way it should be looked at rather than absorbed."""
    assert len(carddemo.resources) == 64
    assert carddemo.flags == []


def test_carddemo_resource_mix(carddemo):
    counts = {}
    for res in carddemo.resources:
        counts[res.kind] = counts.get(res.kind, 0) + 1
    assert counts == {"PROGRAM": 18, "TRANSACTION": 18, "MAPSET": 17, "FILE": 8,
                      "LIBRARY": 2, "TDQUEUE": 1}


def test_carddemo_binds_every_file_to_a_real_dataset(carddemo):
    """The payoff edge. Eight CICS file names, eight VSAM datasets - the join a COBOL
    manifest cannot make and a JCL job cannot make either."""
    bound = {res.name: ref.name
             for res in carddemo.resources if res.kind == "FILE"
             for ref in res.references if ref.kind == "dataset"}
    assert len(bound) == 8
    assert bound["ACCTDAT"] == "AWS.M2.CARDDEMO.ACCTDATA.VSAM.KSDS"
    assert bound["CXACAIX"] == "AWS.M2.CARDDEMO.CARDXREF.VSAM.AIX.PATH"


def test_carddemo_transactions_reach_their_programs(carddemo):
    runs = {res.name: ref.name
            for res in carddemo.resources if res.kind == "TRANSACTION"
            for ref in res.references if ref.kind == "program"}
    assert len(runs) == 18
    assert runs["CAUP"] == "COACTUPC"
    assert runs["CM00"] == "COMEN01C"


def test_carddemo_td_queue_is_the_internal_reader(carddemo):
    """DEFINE TDQUEUE(JOBS) TYPE(EXTRA) DDNAME(INREADER) - this is how the online system
    submits batch work, and it is invisible to every other tool in the family."""
    jobs = next(r for r in carddemo.resources if r.kind == "TDQUEUE")
    assert jobs.name == "JOBS"
    assert jobs.attributes["TYPE"] == "EXTRA"
    # `file`, not `dataset`: INREADER is a ddname. A `dataset INREADER` row reads as a
    # catalogued dataset of that name and joins to nothing.
    assert [(r.field, r.kind, r.name) for r in jobs.references] == [
        ("DDNAME", "file", "INREADER")]


def test_carddemo_line_numbers_are_real(carddemo):
    """Provenance on a 505-line deck: the first FILE is on line 1 and its DSNAME on 2."""
    acct = next(r for r in carddemo.resources if r.name == "ACCTDAT")
    assert acct.line == 1
    assert next(r for r in acct.references if r.kind == "dataset").line == 2


def test_carddemo_has_no_group_to_list_membership(carddemo):
    """Recorded because it bounds what this corpus can prove: with no ADD and no SIT, the
    install closure cannot be tested here at all."""
    assert carddemo.lists == {}
    assert list(carddemo.groups) == ["CARDDEMO"]


# --------------------------------------------------------------------------- #
# IBM example-health-apis - a deck instream in a JCL job, mixed case
# --------------------------------------------------------------------------- #

def test_carddemo_lineage_maps_every_transaction_to_its_program(carddemo):
    lineage = build_cics_lineage(carddemo)
    assert len(lineage["transactions"]) == 18
    assert all(t["runs"] for t in lineage["transactions"])


def test_carddemo_has_no_entry_points_and_that_is_the_honest_answer(carddemo):
    """CardDemo defines no TERMINAL, URIMAP or TCPIPSERVICE, and its one TDQUEUE has no
    trigger. So nothing in the definitions starts any of its eighteen transactions - which
    is true, and is exactly how a real online application looks: users type the id, and
    the programs chain with RETURN TRANSID. The flag has to say that rather than let the
    reader conclude the application is dead."""
    lineage = build_cics_lineage(carddemo)
    assert lineage["entryPoints"] == []
    assert len(lineage["unreachable"]) == 18
    flag = next(f for f in lineage["flags"] if "started by nothing" in f)
    assert "not evidence they are dead" in flag


def test_hcaz_deck_is_found_inside_the_jcl(hcaz):
    """The JCL wrapper - job card, copyright, SET statements, five DD statements - is
    stripped, and only the DFHCSDUP SYSIN is parsed."""
    assert len(hcaz.resources) == 42
    assert not any("before the first command" in f for f in hcaz.flags)


def test_hcaz_line_numbers_survive_the_strip(hcaz):
    """Blank lines stand in for the wrapper so a statement still reports the line it
    occupies in the file the reader has open, not its offset within the extracted deck."""
    hcaz_txn = next(r for r in hcaz.resources
                    if r.kind == "TRANSACTION" and r.name == "HCAZ")
    assert hcaz_txn.line == 32


def test_hcaz_carries_the_group_to_list_membership_carddemo_lacks(hcaz):
    assert hcaz.lists["HCAZLIST"].groups == ["HCAZMOBL"]
    assert hcaz.groups["HCAZMOBL"].lists == ["HCAZLIST"]


def test_hcaz_flags_only_the_two_unapplied_commands(hcaz):
    assert sorted(f.split(":")[1].strip().split()[0] for f in hcaz.flags) == [
        "DELETE", "REMOVE"]


# --------------------------------------------------------------------------- #
# the manifest, over real definitions
# --------------------------------------------------------------------------- #

def test_carddemo_manifest_separates_the_two_directions(carddemo):
    manifest = build_cics_artifacts(carddemo)
    assert len(manifest["provides"]) == 64
    kinds = {}
    for row in manifest["artifacts"]:
        kinds[row["kind"]] = kinds.get(row["kind"], 0) + 1
    # 18 programs a transaction runs; 8 VSAM datasets + 1 load library; 3 transactions
    # named by a PROGRAM's TRANSID; and INREADER, which is a `file` and not a `dataset` -
    # it is the DDNAME of the extrapartition TDQUEUE, and what it points at is on the
    # region startup job. bind_jcl_region turns it into a dataset; nothing else can.
    assert kinds == {"program": 18, "dataset": 9, "cics-transaction": 3, "file": 1}


def test_carddemo_manifest_excludes_only_ibms_and_the_unregistered_kind(carddemo):
    """Three excluded rows out of a 64-definition deck: IBM's DFHCICST profile and
    DFHTCL00 transaction class, plus the LSR pool number, whose kind mainframe-common does
    not register yet. Every one of them is named with the reason."""
    manifest = build_cics_artifacts(carddemo)
    assert {(r["name"], r["category"]) for r in manifest["excluded"]} == {
        ("DFHCICST", "ibm-runtime"), ("DFHTCL00", "ibm-runtime"),
        ("1", "not-retrievable-yet")}


def test_carddemo_manifest_is_conflict_free(carddemo):
    """One deck, one group - so nothing is defined twice. Worth asserting: the conflict
    rule must not fire on a clean deck, or its firing means nothing on a dirty one."""
    manifest = build_cics_artifacts(carddemo)
    assert not any("neither definition is preferred" in f for f in manifest["flags"])


def test_carddemo_installs_once_a_grplist_is_supplied(carddemo):
    """CardDemo has no ADD GROUP/LIST of its own, so the membership is supplied here to
    exercise the closure end to end - and the flag says the resources landed outside it."""
    region = parse_csd((CORPUS / "CARDDEMO.CSD").read_text(encoding="utf-8"),
                       source_name="CARDDEMO.CSD")
    parse_sit(" DFHSIT TYPE=CSECT,APPLID=CICSPRDA,GRPLIST=(APPLIST)\n", region=region)
    apply_install_state(region)
    manifest = build_cics_artifacts(region)
    assert manifest["region"] == "CICSPRDA"
    assert all(p["installed"] == "defined-not-installed" for p in manifest["provides"])
    assert any("64 of 64 definitions are in no group" in f for f in manifest["flags"])


def test_hcaz_mixed_case_is_normalised(hcaz):
    runs = {r["name"]: r for r in provides(hcaz) if r["kind"] == "cics-transaction"}
    assert "HCAZ" in runs
    txn = next(r for r in hcaz.resources if r.kind == "TRANSACTION" and r.name == "HCAZ")
    assert [(r.field, r.name) for r in txn.references] == [("PROGRAM", "HCAZMENU")]


# --------------------------------------------------------------------------- #
# KICKS - the macro-table era, from a real estate rather than from the manuals
# --------------------------------------------------------------------------- #

@pytest.fixture(scope="module")
def kicks():
    region = None
    for name in ("KIKPCTDO.jcl", "KIKPPTDO.jcl", "KIKFCTDO.jcl"):
        region = parse_tables(_text(name), source_name=name, region=region)
    return region


def test_a_macro_deck_arrives_instream_in_an_assemble_job():
    """Not a bare member: KICKS ships each table as a complete PGM=IFOX00 job. Passed the
    job whole, the assembler lexer reads forty lines of JCL as statements, finds no table
    macro, and reports a deck that contributed nothing."""
    assert source_kind(_text("KIKPCTDO.jcl")) == KIND_MACRO
    assert source_kind(_text("KIKSITDO.jcl")) == KIND_SIT


def test_the_kicks_tables_parse_completely(kicks):
    counts = {}
    for res in kicks.resources:
        counts[res.kind] = counts.get(res.kind, 0) + 1
    assert counts == {"PROGRAM": 43, "TRANSACTION": 25, "MAPSET": 13, "FILE": 4}


def test_an_hlasm_remark_is_not_part_of_the_program_name(kicks):
    """`CSGM KIKPCT TYPE=ENTRY,TRANSID=CSGM,PROGRAM=KSGMPGM NO REFRESH` - the remark
    follows a blank. Read as operand text the program becomes `KSGMPGM NO REFRESH`, a name
    that resolves to nothing, in a row that looks completely ordinary."""
    csgm = next(r for r in kicks.resources
                if r.kind == "TRANSACTION" and r.name == "CSGM")
    assert [r.name for r in csgm.references] == ["KSGMPGM"]


def test_a_mapset_can_be_spelt_program_plus_usage_map(kicks):
    """KICKS's PPT writes `PROGRAM=KSGMAP,USAGE=MAP`. Read by the operand name alone,
    every map in the region is reported as a program."""
    assert any(r.kind == "MAPSET" and r.name == "KSGMAP" for r in kicks.resources)
    assert not any(r.kind == "PROGRAM" and r.name == "KSGMAP" for r in kicks.resources)


def test_a_non_ibm_macro_spelling_is_read_and_flagged(kicks):
    """KIKPCT is DFHPCT's shape under another name. Read as IBM's, and SAID to have been -
    the assumption holds while the operands match, and a site macro with its own operand
    vocabulary would not be caught by it."""
    assert any("KIKPCT as DFHPCT" in f for f in kicks.flags)


def test_every_kicks_file_has_a_name_and_nothing_behind_it(kicks):
    """A real FCT, and not one DSNAME in it. This is what bind_jcl_region is for."""
    files = [r for r in kicks.resources if r.kind == "FILE"]
    assert files
    for res in files:
        assert not any(r.kind == "dataset" for r in res.references)
        assert any("no DSNAME" in f for f in res.flags)


def test_the_real_sit_names_its_tables_in_its_own_spelling():
    """FCT=DO under a KIKSIT is the member KIKFCTDO. Asking the estate for DFHFCTDO gets a
    not-found that is about this package, not about the estate."""
    region = parse_sit(_text("KIKSITDO.jcl"), source_name="KIKSITDO.jcl")
    assert region.macro_prefix == "KIK"
    members = dict((p, m) for p, m, _ in table_members(region))
    assert members["FCT"] == "KIKFCTDO"
    assert members["PCT"] == "KIKPCTDO"


def test_the_real_sit_has_no_grplist_and_says_so():
    """A macro-era region installs by table suffix, not by GRPLIST - so the CSD-era
    install closure genuinely cannot decide it, and the flag has to say that rather than
    leaving a reader to assume nothing is installed."""
    region = parse_sit(_text("KIKSITDO.jcl"), source_name="KIKSITDO.jcl")
    assert region.grplist == []
    assert any("names no GRPLIST" in f for f in region.flags)


# --------------------------------------------------------------------------- #
# a real BMS mapset
# --------------------------------------------------------------------------- #

def test_a_real_mapset_is_mostly_unnamed_literals():
    """180 fields, 6 of them named. The rest are screen literals, and the rule that an
    unnamed DFHMDF generates no symbolic data names is what keeps this map from inventing
    870 COBOL fields that do not exist."""
    view = build_bms_lineage(parse_bms(_text("DOGEMMAP.bms"), source_name="DOGEMMAP.bms"))
    assert len(view["fields"]) == 180
    named = [f for f in view["fields"] if f["field"]]
    assert len(named) == 6
    assert all(f["symbolic"] == [] for f in view["fields"] if not f["field"])


def test_a_real_named_field_generates_its_five_cobol_names():
    view = build_bms_lineage(parse_bms(_text("DOGEMMAP.bms"), source_name="DOGEMMAP.bms"))
    avail = next(f for f in view["fields"] if f["field"] == "AVAIL")
    assert {s["name"] for s in avail["symbolic"]} == {
        "AVAILL", "AVAILF", "AVAILA", "AVAILI", "AVAILO"}
    assert avail["pos"] == "(06,17)" and avail["length"] == "19"
