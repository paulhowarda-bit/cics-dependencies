"""The cross-repository binder, against a REAL peer manifest.

``tests/fixtures/custinq.asm.artifacts.json`` was produced by running
``asm-dependencies`` over its own ``examples/custinq.asm`` - not written by hand. A
hand-written fixture passes forever while the real shape drifts underneath it, and the
drift is silent: a manifest nobody managed to bind looks exactly like one nobody tried to
bind. ``tools/refresh_fixture.py --check`` runs here for that reason.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from cics_dependencies import PROGRAM_BINDING_API_VERSION
from cics_dependencies.csd import parse_csd
from cics_dependencies.install import apply_install_state
from cics_dependencies.sit import parse_sit
from cics_dependencies.views import bind_program_artifacts

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "tests" / "fixtures" / "custinq.asm.artifacts.json"
DECK = REPO / "examples" / "custinq.csd"


@pytest.fixture(scope="module")
def bound():
    region = apply_install_state(
        parse_csd(DECK.read_text(encoding="utf-8"), source_name="custinq.csd"))
    peer = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return bind_program_artifacts(peer, region)


def _row(manifest, name):
    return next(r for r in manifest["artifacts"] if r["artifact"] == name)


def test_the_fixture_contract_still_holds():
    proc = subprocess.run([sys.executable, str(REPO / "tools" / "refresh_fixture.py"),
                           "--check"], capture_output=True, text=True, cwd=str(REPO))
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_the_payoff_edge_a_cics_file_reaches_its_vsam_dataset(bound):
    """The whole reason this package exists. The assembler manifest says CUSTINQ reads
    FILE('CUSTMAST') and cannot say what that is; the CSD says PROD.CUSTOMER.MASTER. Now a
    batch job writing that dataset and this online read are the same graph node."""
    row = _row(bound, "CUSTMAST")
    assert row["dataset"] == "PROD.CUSTOMER.MASTER"
    assert row["definition"]["resourceType"] == "FILE"


def test_observed_and_permitted_access_are_both_kept(bound):
    """'permitted update, never updated' is a finding. Overwriting the program's io with
    the definition's makes every read-only module look like an updater; dropping the
    definition's loses the finding."""
    row = _row(bound, "CUSTMAST")
    assert row["io"] == "read"                 # what the module does
    assert row["permittedIo"] == "read-write"  # what the region allows
    assert "different questions" in row["ioMeaning"]


def test_a_transaction_row_gains_the_program_it_runs(bound):
    assert _row(bound, "CINQ")["runs"] == "CUSTINQ"


def test_a_queue_binds_to_a_tsmodel_by_prefix_and_says_so(bound):
    row = _row(bound, "CUSTLOG")
    assert row["boundVia"] == "prefix"
    assert row["definition"]["prefix"] == "CUSTLOG"
    assert "not by name" in row["definition"]["note"]


def test_a_bms_map_is_unbound_and_the_reason_says_that_is_correct(bound):
    """CUSTM02 is a MAP inside the CUSTSET mapset. No CSD ever defines it, so 'unbound'
    here is the right answer and must not read as a missing definition."""
    unbound = bound["cicsBinding"]["unbound"]
    assert [u["artifact"] for u in unbound] == ["CUSTM02"]
    assert "only the mapset is ever a CSD resource" in unbound[0]["reason"]
    assert _row(bound, "CUSTSET")["boundVia"] == "definition"


def test_rows_this_package_knows_nothing_about_are_passed_through(bound):
    """A Db2 table is none of this package's business and must come out untouched."""
    row = _row(bound, "PRODDB.CUSTOMER")
    assert row["kind"] == "db2-table"
    assert "definition" not in row and "boundVia" not in row


def test_the_binder_reports_its_own_contract_version(bound):
    assert bound["cicsBinding"]["apiVersion"] == PROGRAM_BINDING_API_VERSION
    assert bound["cicsBinding"]["bound"] == 5


def test_the_input_manifest_is_not_mutated():
    """It takes a plain dict and returns a NEW one. A caller that binds against two
    regions must not have the first run's keys still on its rows."""
    region = parse_csd(DECK.read_text(encoding="utf-8"), source_name="custinq.csd")
    peer = json.loads(FIXTURE.read_text(encoding="utf-8"))
    before = json.dumps(peer, sort_keys=True)
    bind_program_artifacts(peer, region)
    assert json.dumps(peer, sort_keys=True) == before


def test_binding_carries_the_installed_state_and_the_region(bound):
    region = apply_install_state(
        parse_csd(DECK.read_text(encoding="utf-8"), source_name="custinq.csd"))
    parse_sit(" DFHSIT TYPE=CSECT,APPLID=CICSAPP1,GRPLIST=(APPLIST)\n", region=region)
    apply_install_state(region)
    out = bind_program_artifacts(json.loads(FIXTURE.read_text(encoding="utf-8")), region)
    assert out["cicsBinding"]["region"] == "CICSAPP1"
    assert _row(out, "CUSTMAST")["definition"]["installed"] == "installed"


def test_a_file_defined_without_a_dsname_says_where_the_dataset_lives():
    """The macro era: an FCT entry usually has no DSNAME, and the binding is a DD on the
    DFHSIP step. The row must say so rather than come back with no dataset and no reason."""
    region = parse_csd(" DEFINE FILE(CUSTMAST) GROUP(G) READ(YES)\n")
    out = bind_program_artifacts(json.loads(FIXTURE.read_text(encoding="utf-8")), region)
    row = _row(out, "CUSTMAST")
    assert "dataset" not in row
    assert "bind_jcl_region" in row["definition"]["note"]
