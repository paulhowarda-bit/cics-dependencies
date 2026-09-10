"""The reverse direction: what the estate says depends on the resources defined here.

A CSD says what the region wires together. It cannot say which of the estate's programs
issue ``READ FILE`` against one of its file definitions - that lives in an index only the
host can read - so the answer arrives through a door and is reported as given, apart from
every view that reads the decks themselves.
"""

import json

from mainframe_artifacts.dependents import DependentsLookup
from mainframe_artifacts.kinds import MANIFEST_KINDS

from cics_dependencies.api import analyze
from cics_dependencies.csd import parse_csd
from cics_dependencies.resources import PROVIDES_KIND
from cics_dependencies.views import FORMAT_DEPENDENTS, build_cics_dependents

DECK = (" DEFINE TRANSACTION(CAUP) GROUP(APPG) PROGRAM(COACTUPC)\n"
        " DEFINE FILE(ACCTDAT) GROUP(APPG) DSNAME(AWS.M2.ACCTDATA)\n"
        " DEFINE MAPSET(COACTUP) GROUP(APPG)\n")

#: What a host index holds. ACCTDAT is read by two programs; the mapset by one; and the
#: transaction is asked about and has nothing depending on it.
_INDEX = {
    "ACCTDAT|file": [
        {"name": "COACTUPC", "kind": "PROGRAM", "via": "READ FILE",
         "match_strength": "qualified"},
        {"name": "COACTVWC", "kind": "PROGRAM", "via": "READ FILE",
         "match_strength": "bare", "detail": "matched on the file name alone"},
    ],
    "COACTUP|MAPSET": [
        {"name": "COACTUPC", "kind": "PROGRAM", "via": "SEND MAP"},
    ],
    "CAUP|cics-transaction": [],
}


def _view(mapping=None, resolver=None):
    region = parse_csd(DECK, source_name="appg.csd")
    return build_cics_dependents(region, DependentsLookup(mapping, resolver))


def _resource(view, name):
    return next(row for row in view["resources"] if row["name"] == name)


# --- the join, on the resource rather than the region --------------------------------

def test_dependents_attach_to_the_resource_that_was_named():
    view = _view(_INDEX)
    # In provides() order - by (kind, name), which is what makes the view stable.
    assert [row["name"] for row in view["resources"]] == ["CAUP", "ACCTDAT", "COACTUP"]
    acctdat = _resource(view, "ACCTDAT")
    assert [d["name"] for d in acctdat["dependents"]] == ["COACTUPC", "COACTVWC"]
    assert acctdat["kind"] == "file"
    assert acctdat["resourceType"] == "FILE"
    assert acctdat["group"] == "APPG"
    # The transaction was asked about and holds nothing - said with an empty list.
    assert _resource(view, "CAUP")["dependents"] == []


def test_a_mapset_is_asked_about_as_the_manifest_word_and_matched_on_the_hosts():
    """The map file wrote MAPSET; the region calls it terminal-map. Both reduce."""
    mapset = _resource(_view(_INDEX), "COACTUP")
    assert mapset["kind"] == "terminal-map"
    assert [d["name"] for d in mapset["dependents"]] == ["COACTUPC"]


def test_the_view_has_the_family_keys_and_the_region_subject_key():
    view = _view(_INDEX)
    assert list(view) == ["format", "formatVersion", "region", "sources", "note",
                          "suppliedBy", "resources", "unanswered", "flags"]
    assert view["format"] == FORMAT_DEPENDENTS


def test_a_row_carries_the_hosts_strength_as_its_own_field():
    rows = _resource(_view(_INDEX), "ACCTDAT")["dependents"]
    assert [d["matchStrength"] for d in rows] == ["qualified", "bare"]
    assert rows[1]["detail"] == "matched on the file name alone"
    assert rows[0]["manifestKind"] == "program"


def test_rows_are_sorted_so_the_hosts_order_cannot_change_the_bytes():
    flipped = dict(_INDEX)
    flipped["ACCTDAT|file"] = list(reversed(_INDEX["ACCTDAT|file"]))
    assert json.dumps(_view(_INDEX)) == json.dumps(_view(flipped))


# --- the vocabulary this package emits ------------------------------------------------

def test_every_kind_this_package_provides_is_in_the_shared_vocabulary():
    """A dependents row whose kind is not in the vocabulary is refused, so a resource
    type this package names had better be in it. This caught fifteen missing CICS words
    when the contract first arrived."""
    assert set(PROVIDES_KIND.values()) <= MANIFEST_KINDS


# --- the three answers ----------------------------------------------------------------

def test_no_lookup_supplied_is_no_view_at_all():
    region = parse_csd(DECK, source_name="appg.csd")
    assert build_cics_dependents(region, None) is None
    assert build_cics_dependents(region, DependentsLookup()) is None


def test_a_resource_the_index_does_not_cover_is_unanswered_not_empty():
    view = _view({"ACCTDAT|file": _INDEX["ACCTDAT|file"]})
    assert [row["name"] for row in view["resources"]] == ["ACCTDAT"]
    assert [row["name"] for row in view["unanswered"]] == ["CAUP", "COACTUP"]
    assert view["unanswered"][0]["reason"] == "the lookup does not cover this resource"


def test_a_lookup_that_breaks_leaves_the_rest_unanswered_and_flagged():
    def boom(name, kind=None):
        raise RuntimeError("index unreachable")

    view = _view(resolver=boom)
    assert view["resources"] == []
    assert len(view["unanswered"]) == 3
    assert "index unreachable" in view["flags"][0]


def test_a_reported_fan_out_cap_reaches_the_view():
    def capped(name, kind=None):
        return ({"rows": _INDEX["ACCTDAT|file"], "truncated": True, "total": 4211}
                if name == "ACCTDAT" else None)

    row = _resource(_view(resolver=capped), "ACCTDAT")
    assert (row["truncated"], row["total"], row["count"]) == (True, 4211, 2)


# --- through analyze() and the bundle -------------------------------------------------

def test_analyze_without_the_parameter_is_the_run_it_always_was():
    analysis = analyze([("appg.csd", DECK)], retrieve=False)
    assert analysis.dependents_lookup is None
    assert analysis.dependents() is None


def test_analyze_asks_the_lookup_once_per_resource():
    calls = []

    def index(name, kind=None):
        calls.append((name, kind))
        return _INDEX.get("{0}|{1}".format(name, kind))

    analysis = analyze([("appg.csd", DECK)], retrieve=False, dependents_resolver=index)
    view = analysis.dependents()
    assert analysis.dependents() is view                # memoised, not re-asked
    assert sorted(calls) == [("ACCTDAT", "file"), ("CAUP", "cics-transaction"),
                             ("COACTUP", "terminal-map")]


def test_a_gathered_bundle_replays_the_reverse_direction(tmp_path):
    from mainframe_artifacts.bundle import open_bundle

    from cics_dependencies.api import gather

    def index(name, kind=None):
        return _INDEX.get("{0}|{1}".format(name, kind))

    live = analyze([("appg.csd", DECK)], retrieve=False,
                   dependents_resolver=index).dependents()
    root = tmp_path / "bundle"
    gather([("appg.csd", DECK)], dest=str(root), dependents_resolver=index)

    bundle = open_bundle(root)
    assert bundle.has_dependents()
    replayed = analyze([("appg.csd", bundle.source())], source_name="appg.csd",
                       bundle=bundle).dependents()
    assert replayed == live
