"""The region startup job binder, against a REAL jcl-dependencies lineage view.

``tests/fixtures/cicsapp1.jcl.lineage.json`` was produced by running `jcl-dependencies`
over this repository's ``examples/cicsapp1.jcl`` - see tools/refresh_fixture.py. On a
macro-era estate this join is not corroboration, it is the ONLY route from a file name to
a dataset, because a DFHFCT entry carries no DSNAME at all.
"""

import json
from pathlib import Path

import pytest

from cics_dependencies.csd import parse_csd
from cics_dependencies.views import bind_jcl_region, build_cics_artifacts

REPO = Path(__file__).resolve().parents[1]
LINEAGE = REPO / "tests" / "fixtures" / "cicsapp1.jcl.lineage.json"
DECK = REPO / "examples" / "appregn.csd"


@pytest.fixture(scope="module")
def lineage():
    return json.loads(LINEAGE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def region(lineage):
    r = parse_csd(DECK.read_text(encoding="utf-8"), source_name="appregn.csd")
    bind_jcl_region(r, lineage)
    return r


def _bound(region, ddname):
    return next(b for b in region.jcl["bound"] if b["ddname"] == ddname)


def test_cics_own_datasets_are_named_and_never_matched_to_a_file(region):
    """DFHCSD, DFHTEMP, DFHINTRA and the trace datasets are the region's own. Matching one
    to a FILE definition would be wrong; omitting them loses what the region is built on."""
    roles = {d["ddname"]: d["dataset"] for d in region.jcl["systemDatasets"]}
    assert roles["DFHCSD"] == "CICSTS.CICSAPP1.DFHCSD"
    assert roles["DFHRPL"] == "PROD.APP.LOADLIB"
    assert "CUSTMAS" not in roles


def test_a_dd_that_agrees_with_the_definition_is_corroboration(region):
    assert "corroborated" in _bound(region, "CUSTMAS")["via"]
    assert _bound(region, "CUSTMAS")["dataset"] == "PROD.CUSTOMER.MASTER"


def test_a_td_queue_ddname_finally_gets_its_dataset(region):
    """A DDNAME is a name awaiting a dataset - kind `file`, not `dataset`. Only the region
    startup job says what it points at, and this is where that arrives."""
    rptq = next(r for r in region.resources if r.name == "RPTQ")
    kinds = [(r.field, r.kind, r.name) for r in rptq.references]
    assert ("DDNAME", "file", "APPRPT") in kinds
    assert ("DDNAME", "dataset", "PROD.APP.REPORT") in kinds
    assert _bound(region, "APPRPT")["resourceType"] == "TDQUEUE"


def test_a_dd_matching_nothing_is_a_finding_not_an_error(region):
    unmatched = region.jcl["unmatched"]
    assert [u["ddname"] for u in unmatched] == ["LEGACYF"]
    assert "macro-era FCT" in unmatched[0]["reason"]
    assert any("match no definition" in f for f in region.flags)


def test_a_macro_era_file_with_no_dsname_is_bound_from_the_jcl(lineage):
    """The case this exists for. A DFHFCT entry gives a name and nothing else; without the
    startup job the row has no dataset at all."""
    region = parse_csd(" DEFINE FILE(CUSTMAS) GROUP(G) READ(YES) UPDATE(YES)\n")
    assert not any(r.kind == "dataset" for r in region.resources[0].references)
    bind_jcl_region(region, lineage)
    dataset = next(r for r in region.resources[0].references if r.kind == "dataset")
    assert dataset.name == "PROD.CUSTOMER.MASTER"
    assert dataset.io == "read-write"          # the access the definition permits
    assert "carries no DSNAME" in dataset.note


def test_a_disagreement_is_reported_and_neither_side_wins(lineage):
    """Same rule as the two-eras conflict: the DD and the definition are two statements
    about one estate, and which is current is not decidable from either text."""
    region = parse_csd(" DEFINE FILE(CUSTMAS) GROUP(G) DSNAME(TEST.CUSTOMER.MASTER)\n"
                       "        READ(YES)\n")
    bind_jcl_region(region, lineage)
    assert _bound(region, "CUSTMAS")["disagreesWith"] == "TEST.CUSTOMER.MASTER"
    flag = next(f for f in region.resources[0].flags if "startup job binds" in f)
    assert "neither is preferred" in flag


def test_a_lineage_view_with_no_region_step_binds_nothing_and_says_so():
    region = parse_csd(DECK.read_text(encoding="utf-8"), source_name="appregn.csd")
    bind_jcl_region(region, {"job": "BATCHJOB", "ddBindings": [
        {"program": "IDCAMS", "step": "S1", "ddname": "SYSIN", "dataset": "A.B"}]})
    assert region.jcl is None
    assert any("no DD statements for a DFHSIP step" in f for f in region.flags)


def test_an_unbound_region_says_nothing_rather_than_saying_empty():
    """`jcl is None` and `jcl == {...empty...}` are different statements about an estate:
    'no startup job was supplied' is not 'the job binds nothing'."""
    region = parse_csd(DECK.read_text(encoding="utf-8"), source_name="appregn.csd")
    assert region.jcl is None


def test_the_bound_dataset_reaches_the_manifest(region):
    manifest = build_cics_artifacts(region)
    names = {row["artifact"] for row in manifest["artifacts"] if row["kind"] == "dataset"}
    assert "PROD.APP.REPORT" in names
