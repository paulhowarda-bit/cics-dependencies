"""The library front end, and the stage-1 closure it drives."""

import json
from pathlib import Path

from fakes.estate import fetch_artifact

from cics_dependencies.api import analyze, summarize

REPO = Path(__file__).resolve().parents[1]
DECK = (REPO / "examples" / "appregn.csd").read_text(encoding="utf-8")
SIT = (REPO / "examples" / "appregn.sit").read_text(encoding="utf-8")


def _sources():
    return [("appregn.csd", DECK)]


def test_a_run_with_no_estate_still_produces_both_views():
    a = analyze(_sources(), retrieve=False)
    assert a.artifacts()["format"] == "cics-dependencies-artifacts"
    assert a.lineage()["format"] == "cics-dependencies-lineage"
    assert a.fetch is not None


def test_without_a_sit_everything_is_unknown():
    a = analyze(_sources(), retrieve=False)
    assert {p["installed"] for p in a.artifacts()["provides"]} == {"unknown"}


def test_with_a_sit_the_region_is_named_and_the_state_is_decided():
    a = analyze(_sources(), sit=("appregn.sit", SIT), retrieve=False)
    assert a.artifacts()["region"] == "CICSAPP1"
    assert {p["installed"] for p in a.artifacts()["provides"]} == {"installed"}


#: A SIT whose GRPLIST names a list the deck does NOT contain - which is what gives the
#: closure something to close over.
SIT_TWO_LISTS = " DFHSIT TYPE=CSECT,APPLID=CICSAPP1,GRPLIST=(APPLIST,RPTLIST,DFHLIST)\n"


def test_a_list_already_in_the_deck_is_never_asked_for():
    """appregn.csd carries `ADD GROUP(APPG) LIST(APPLIST)`, so APPLIST is in hand. Asking
    for a member already held is the classic way a closure doubles its round-trips."""
    a = analyze(_sources(), sit=("t.sit", SIT_TWO_LISTS), fetcher=fetch_artifact)
    assert "APPLIST" not in {row["member"] for row in a.prefetch.report()["members"]}


def test_the_closure_retrieves_a_list_and_then_the_groups_it_names():
    """Two rounds, and the second is the point. RPTLIST is fetched because GRPLIST names
    it and the deck does not hold it; REPORTG is fetched because RPTLIST adds it - which
    is only knowable AFTER RPTLIST has been read. A closure that stopped at one round
    would report a region holding definitions for a fraction of what it installs, and
    nothing in the output would say so."""
    a = analyze(_sources(), sit=("t.sit", SIT_TWO_LISTS), fetcher=fetch_artifact)
    members = {row["member"]: row["status"] for row in a.prefetch.report()["members"]}
    assert members["RPTLIST"] == "fetched"
    assert members["REPORTG"] == "fetched"
    names = {r.name for r in a.region.resources}
    assert {"APRP", "APPRPT01", "RPTMAST"} <= names


def test_an_ibm_list_is_never_asked_for():
    """GRPLIST names DFHLIST in every real region. Fetching it spends a round-trip on
    several hundred rows this package excludes as ibm-runtime anyway, and a not-found
    against it reads as a hole in the shop's model."""
    a = analyze(_sources(), sit=("t.sit", SIT_TWO_LISTS), fetcher=fetch_artifact)
    assert "DFHLIST" not in {row["member"] for row in a.prefetch.report()["members"]}


def test_the_sit_table_suffixes_are_asked_for_by_member_name():
    """PLTPI=PI means the member DFHPLTPI. Asked for and not found here, which is the
    honest answer - the fake estate has no PLT."""
    a = analyze(_sources(), sit=("appregn.sit", SIT), fetcher=fetch_artifact)
    members = {row["member"]: row["status"] for row in a.prefetch.report()["members"]}
    assert members["DFHPLTPI"] == "not-found"
    assert members["DFHXLTSD"] == "not-found"


def test_no_fetch_says_never_looked_for_rather_than_not_found():
    """The distinction the whole report exists to keep: 'the estate had nothing' and
    'the estate was never asked' are different facts about an estate."""
    a = analyze(_sources(), sit=("appregn.sit", SIT), retrieve=False)
    statuses = {row["status"] for row in a.prefetch.report()["members"]}
    assert statuses == {"no-service"}
    assert a.prefetch.report()["serviceAvailable"] is False


def test_bind_jcl_invalidates_the_cached_views():
    """A view built before the binding would be the pre-binding one, served forever."""
    lineage = json.loads(
        (REPO / "tests" / "fixtures" / "cicsapp1.jcl.lineage.json").read_text("utf-8"))
    a = analyze(_sources(), retrieve=False)
    before = {r["artifact"] for r in a.artifacts()["artifacts"]}
    a.bind_jcl(lineage)
    after = {r["artifact"] for r in a.artifacts()["artifacts"]}
    assert "PROD.APP.REPORT" not in before
    assert "PROD.APP.REPORT" in after


def test_binding_through_the_analysis_takes_a_plain_dict():
    manifest = json.loads(
        (REPO / "tests" / "fixtures" / "custinq.asm.artifacts.json").read_text("utf-8"))
    a = analyze([("custinq.csd",
                  (REPO / "examples" / "custinq.csd").read_text("utf-8"))],
                retrieve=False)
    assert a.bind(manifest)["cicsBinding"]["bound"] == 5


def test_the_summary_includes_the_zeros():
    """A scoreboard that omits what was not found is the one that misleads."""
    a = analyze(_sources(), sit=("appregn.sit", SIT), retrieve=False)
    text = "\n".join(summarize(a))
    assert "region:" in text and "excluded:" in text and "flags:" in text
    assert "NOT RETRIEVED" in text          # -- with no estate, everything is missing
    assert text.isascii()                    # the Windows console is cp1252


def test_analyze_needs_a_source():
    try:
        analyze([])
    except ValueError as exc:
        assert "at least one" in str(exc)
    else:
        raise AssertionError("analyze([]) should not be a silent empty region")
