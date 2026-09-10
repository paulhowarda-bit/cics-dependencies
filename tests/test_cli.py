"""The command line, run for real - it is what most people will actually use."""

import json
from pathlib import Path

from cics_dependencies.cli import run

REPO = Path(__file__).resolve().parents[1]
DECK = str(REPO / "examples" / "appregn.csd")
SIT = str(REPO / "examples" / "appregn.sit")
JCL = str(REPO / "tests" / "fixtures" / "cicsapp1.jcl.lineage.json")
ASM = str(REPO / "tests" / "fixtures" / "custinq.asm.artifacts.json")
FAKE = "fakes.estate:fetch_artifact"        # tests/ is on the path (pyproject pythonpath)


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


def test_gather_then_replay_reproduces_the_views(tmp_path):
    """The offline half of the design: a bundle gathered where the estate is reachable
    must model to the same bytes on a box that cannot reach it. Nothing exercised
    --from-bundle before this, and it had been dead - an AttributeError reported as an
    internal error - for as long as it has existed."""
    bundle, live, offline = (str(tmp_path / "b"), str(tmp_path / "live"),
                             str(tmp_path / "off"))
    assert run([DECK, "--sit", SIT, "--outdir", str(tmp_path / "g"), "-q",
                "--fetcher", FAKE, "--gather-only", bundle]) == 0
    assert run([DECK, "--sit", SIT, "--outdir", live, "-q", "--fetcher", FAKE]) == 0
    # No --fetcher at all on the replay: the bundle is the service.
    assert run([DECK, "--sit", SIT, "--outdir", offline, "-q",
                "--from-bundle", bundle]) == 0
    for name in ("appregn.csd.artifacts.json", "appregn.csd.lineage.json"):
        assert (Path(offline) / name).read_text("utf-8") == \
            (Path(live) / name).read_text("utf-8")


def test_a_bundle_that_is_not_there_is_an_operator_error_not_a_crash(tmp_path):
    assert run([DECK, "--sit", SIT, "--outdir", _out(tmp_path), "-q",
                "--from-bundle", str(tmp_path / "nope")]) == 2


def test_gathering_and_replaying_in_one_run_is_refused(tmp_path):
    """The other four front-ends refuse this; silently honouring one flag and ignoring
    the other is how an operator ends up believing a bundle was written."""
    assert run([DECK, "--sit", SIT, "--outdir", _out(tmp_path), "-q",
                "--gather-only", str(tmp_path / "b"),
                "--from-bundle", str(tmp_path / "b")]) == 2


def test_gather_records_the_reverse_direction_it_was_given(tmp_path):
    """--gather-only is the run that happens where the INDEX is reachable, so a door the
    CLI forgets to hand it is a bundle that replays the estate and not the reverse
    direction - and the modelling box has no way to notice."""
    from mainframe_artifacts.bundle import open_bundle

    bundle = str(tmp_path / "b")
    assert run([DECK, "--sit", SIT, "--outdir", _out(tmp_path), "-q",
                "--gather-only", bundle,
                "--dependents-resolver", "fakes.index:dependents"]) == 0
    assert open_bundle(bundle).has_dependents()

    out = str(tmp_path / "o2")
    assert run([DECK, "--sit", SIT, "--outdir", out, "-q",
                "--from-bundle", bundle]) == 0
    dep = json.loads((Path(out) / "appregn.csd.dependents.json").read_text("utf-8"))
    row = next(r for r in dep["resources"] if r["name"] == "CUSTMAS")
    assert [d["name"] for d in row["dependents"]] == ["CUSTINQ1"]


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
