"""DFHCSDUP's printed listing, which is what a whole-region CSD usually IS.

A region's definition deck is long gone in most estates; what a site can hand over is the
utility's own ``LIST ... OBJECTS`` report. It carries no command verb anywhere, so read as
a deck it produced ZERO resources and one "text before the first command" flag per line -
a flag list longer than the member, wrapped around an empty region that looks exactly like
a region whose deck defined nothing.
"""

from pathlib import Path

from cics_dependencies.csd import parse_csd, provides
from cics_dependencies.detect import KIND_CSD, looks_like_csd_report, source_kind
from cics_dependencies.views import build_cics_artifacts, build_cics_lineage

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"

#: One object of each shape the report has: the ASA carriage control in column 1, the
#: right-margin print timestamp on the header, the indented attributes, the report-only
#: DEFINETIME/CHANGETIME, and DFHCSDUP's own message trailer.
REPORT = (
    " DFHCSDUP - CICS DEFINITION FILE UTILITY PROGRAM                     15.206 23:09\n"
    " LIST GROUP(RPTG) OBJECTS\n"
    " TRANSACTION(RPTA)       GROUP(RPTG)"
    + " " * 44 + "15.206 23:09\n"
    "                         PROGRAM(RPTMAIN)       TWASIZE(0)\n"
    "                         ROUTABLE(NO)           REMOTESYSTEM(RSYB)\n"
    "                         DEFINETIME(15/07/25 23:09:21)\n"
    "                         CHANGETIME(15/07/25 23:09:21)\n"
    " DFH5123 I PRIMARY CSD CLOSED; DDNAME: DFHCSD\n"
    " DFH5109 I END OF DFHCSDUP UTILITY JOB.  HIGHEST RETURN CODE WAS:   0\n"
)


def _region(text=REPORT, name="region.csd"):
    return parse_csd(text, source_name=name)


def test_a_listing_is_recognised_as_one():
    assert looks_like_csd_report(REPORT)
    assert source_kind(REPORT, "region.csd") == KIND_CSD


def test_a_deck_is_not_mistaken_for_a_listing():
    """It is the ABSENCE of a command verb that decides. A deck's own
    ``DEFINE FILE(x) GROUP(y)`` has the same shape once the verb is taken off."""
    deck = " DEFINE FILE(X) GROUP(G) DSNAME(A.B.C)\n"
    assert not looks_like_csd_report(deck)


def test_the_objects_come_out_with_their_attributes():
    region = _region()
    assert [(r.kind, r.name, r.group) for r in region.resources] == [
        ("TRANSACTION", "RPTA", "RPTG")]
    assert region.resources[0].attributes["PROGRAM"] == "RPTMAIN"
    # The attribute that is lost when a 121-column line is cut at column 72.
    assert region.resources[0].attributes["REMOTESYSTEM"] == "RSYB"


def test_the_report_furniture_does_not_become_operands():
    """The right-margin stamp is the REPORT's print time, not the definition's: read as
    data it becomes bare operands named `15.206` and `23:09` on every object."""
    attrs = _region().resources[0].attributes
    assert "15.206" not in attrs and "23:09" not in attrs
    # The definition's own times ARE the source speaking, so they are kept.
    assert attrs["DEFINETIME"] == "15/07/25 23:09:21"


def test_the_listing_says_which_dialect_answered():
    assert any("DFHCSDUP LIST report output" in f for f in _region().flags)


def test_a_message_ends_the_object_above_it():
    """A member is often several jobs concatenated. Absorbed as attributes, the banner and
    command echo that start the next segment hand the last object of the previous one the
    GROUP named in the next segment's LIST command - reported with no flag at all."""
    two = REPORT + (
        " DFHCSDUP - CICS DEFINITION FILE UTILITY PROGRAM                 15.206 23:11\n"
        " LIST GROUP(RPTG2) OBJECTS\n"
        " PROGRAM(RPTMAIN)        GROUP(RPTG2)\n"
        "                         LANGUAGE(COBOL)\n")
    kinds = {(r.kind, r.name): r.group for r in _region(two).resources}
    assert kinds[("TRANSACTION", "RPTA")] == "RPTG"
    assert kinds[("PROGRAM", "RPTMAIN")] == "RPTG2"


def test_a_nonzero_return_code_is_reported():
    """A listing from a job that did not end cleanly may not list everything."""
    bad = REPORT.replace("HIGHEST RETURN CODE WAS:   0",
                         "HIGHEST RETURN CODE WAS:   8")
    assert any("highest return code 8" in f for f in _region(bad).flags)


def test_the_flag_list_cannot_be_longer_than_the_source():
    """The failure this item is about, stated as a property: 320,280 lines produced
    482,849 flags. Whatever a source is, a report ABOUT it is shorter than a transcript
    OF it."""
    region = _region((EXAMPLES / "regndump.csd").read_text())
    flags = build_cics_artifacts(region)["flags"]
    assert len(flags) < len((EXAMPLES / "regndump.csd").read_text().splitlines())
    assert region.resources


def test_the_example_recovers_every_object_it_lists():
    region = _region((EXAMPLES / "regndump.csd").read_text(), "regndump.csd")
    assert [(r.kind, r.name) for r in region.resources] == [
        ("FILE", "RPTFILE"), ("TRANSACTION", "RPTA"),
        ("PROGRAM", "RPTMAIN"), ("MAPSET", "RPTSET")]
    lineage = build_cics_lineage(region)
    row = next(t for t in lineage["transactions"] if t["transaction"] == "RPTA")
    # Both answers a cut line destroys: which program runs, and where it is routed.
    assert (row["runs"], row["routedTo"]) == ("RPTMAIN", "RSYB")
    assert not any(r.get("incomplete") for r in provides(region))
