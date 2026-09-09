"""The command line, run for real - it is what most people will actually use."""

import json
from pathlib import Path

from cics_dependencies.cli import run

REPO = Path(__file__).resolve().parents[1]
DECK = str(REPO / "examples" / "appregn.csd")
SIT = str(REPO / "examples" / "appregn.sit")
JCL = str(REPO / "tests" / "fixtures" / "cicsapp1.jcl.lineage.json")
ASM = str(REPO / "tests" / "fixtures" / "custinq.asm.artifacts.json")


def _out(tmp_path):
    return str(tmp_path / "o")


def test_a_default_run_writes_both_views_and_both_reports(tmp_path):
    assert run([DECK, "--outdir", _out(tmp_path), "-q", "--no-fetch"]) == 0
    written = sorted(p.name for p in Path(_out(tmp_path)).glob("*.json"))
    assert written == ["appregn.csd.artifacts.json", "appregn.csd.fetch.json",
                       "appregn.csd.lineage.json", "appregn.csd.prefetch.json"]


def test_target_narrows_what_is_written(tmp_path):
    assert run([DECK, "--outdir", _out(tmp_path), "-q", "--no-fetch",
                "--target", "lineage"]) == 0
    names = {p.name for p in Path(_out(tmp_path)).glob("*.json")}
    assert "appregn.csd.lineage.json" in names
    assert "appregn.csd.artifacts.json" not in names


def test_the_sit_flag_decides_the_installed_state(tmp_path):
    assert run([DECK, "--sit", SIT, "--outdir", _out(tmp_path), "-q", "--no-fetch"]) == 0
    manifest = json.loads(
        (Path(_out(tmp_path)) / "appregn.csd.artifacts.json").read_text("utf-8"))
    assert manifest["region"] == "CICSAPP1"
    assert {p["installed"] for p in manifest["provides"]} == {"installed"}


def test_several_decks_make_one_region_and_the_conflict_is_flagged(tmp_path):
    legacy = str(REPO / "examples" / "legacy.csd")
    assert run([DECK, legacy, "--outdir", _out(tmp_path), "-q", "--no-fetch"]) == 0
    manifest = json.loads(
        (Path(_out(tmp_path)) / "appregn.csd.artifacts.json").read_text("utf-8"))
    assert manifest["sources"] == ["appregn.csd", "legacy.csd"]
    assert any("neither definition is preferred" in f for f in manifest["flags"])


def test_bind_jcl_puts_the_datasets_in_the_manifest(tmp_path):
    assert run([DECK, "--bind-jcl", JCL, "--outdir", _out(tmp_path), "-q",
                "--no-fetch"]) == 0
    manifest = json.loads(
        (Path(_out(tmp_path)) / "appregn.csd.artifacts.json").read_text("utf-8"))
    assert "PROD.APP.REPORT" in {r["artifact"] for r in manifest["artifacts"]}


def test_bind_jcl_rejects_the_wrong_view_by_name(tmp_path):
    """Pointed at the ARTIFACTS view by mistake, the binding would find no ddBindings,
    bind nothing, and say nothing. So the format is checked rather than the content."""
    wrong = tmp_path / "wrong.json"
    wrong.write_text(json.dumps({"format": "jcl-dependencies-artifacts"}), "utf-8")
    assert run([DECK, "--bind-jcl", str(wrong), "--outdir", _out(tmp_path), "-q",
                "--no-fetch"]) == 2


def test_bind_program_writes_one_bound_manifest_per_input(tmp_path):
    deck = str(REPO / "examples" / "custinq.csd")
    assert run([deck, "--bind-program", ASM, "--outdir", _out(tmp_path), "-q",
                "--no-fetch"]) == 0
    bound = json.loads(
        (Path(_out(tmp_path)) / "custinq.asm.artifacts.bound.json").read_text("utf-8"))
    assert bound["cicsBinding"]["bound"] == 5


def test_a_missing_source_is_an_operator_error_not_a_crash(tmp_path):
    assert run([str(tmp_path / "nope.csd"), "--outdir", _out(tmp_path), "-q"]) == 2


def test_a_deck_that_defines_nothing_still_writes_its_views(tmp_path):
    """An empty result is a real result. A run that wrote nothing would be
    indistinguishable from a run that failed."""
    empty = tmp_path / "empty.csd"
    empty.write_text("*** nothing but a comment\n", "utf-8")
    assert run([str(empty), "--outdir", _out(tmp_path), "-q", "--no-fetch"]) == 0
    manifest = json.loads(
        (Path(_out(tmp_path)) / "empty.csd.artifacts.json").read_text("utf-8"))
    assert manifest["provides"] == [] and manifest["artifacts"] == []
