"""The edge table is the source of truth, so it is the thing most worth checking.

Two of these tests reach into mainframe-artifacts on purpose. ``resources.py`` makes a
CLAIM about the upstream registry - these kinds are registered, those are not - and a
claim about another repository rots silently. Asserting it here means the day someone
adds the CICS kinds upstream, this suite goes red and says so, which is the prompt to stop
routing them to ``excluded``.
"""

import pytest

from mainframe_artifacts.artifact_service import EXT_FOR_TYPE
from mainframe_artifacts.fetch import _KIND_TYPE

from cics_dependencies.resources import (
    ALL_KINDS, ATTRIBUTES, FCT_SERVREQ, FILE_ACCESS, MACRO_LISTS, MACRO_RESOURCE,
    NO_IO_KINDS, REGISTERED_KINDS, UNREGISTERED_KINDS, Attr, attributes_for,
)


# --------------------------------------------------------------------------- #
# the table is internally consistent
# --------------------------------------------------------------------------- #

def test_every_edge_names_a_known_kind():
    """An Attr whose kind is not in the vocabulary produces a manifest row no consumer
    has a rule for - and nothing else in the pipeline would notice."""
    for resource, attrs in ATTRIBUTES.items():
        for attr in attrs:
            assert attr.kind in ALL_KINDS, (resource, attr.field, attr.kind)


def test_no_resource_declares_the_same_field_twice():
    """A duplicate field silently doubles an edge, or worse, disagrees with itself about
    the kind."""
    for resource, attrs in ATTRIBUTES.items():
        fields = [a.field for a in attrs]
        assert len(fields) == len(set(fields)), (resource, fields)


def test_every_edge_states_a_relation():
    """``runs`` and ``triggers`` are both TRANSACTION edges and a graph loader that
    conflates them cannot tell a menu from a queue-driven task, so the relation is not
    optional decoration."""
    for resource, attrs in ATTRIBUTES.items():
        for attr in attrs:
            assert attr.relation, (resource, attr.field)


def test_the_macro_era_maps_onto_resources_the_table_knows():
    for macro, resource in MACRO_RESOURCE.items():
        assert resource in ATTRIBUTES, (macro, resource)


def test_the_macro_list_decks_name_known_kinds():
    for macro, (_operand, kind, relation) in MACRO_LISTS.items():
        assert kind in ALL_KINDS, (macro, kind)
        assert relation


def test_macro_field_defaults_to_the_csd_spelling():
    assert Attr("PROGRAM", "program", "runs").macro_field() == "PROGRAM"
    assert Attr("DSNAME", "dataset", "binds", macro="DSCNAME").macro_field() == "DSCNAME"


def test_permitted_access_is_only_ever_read_or_write():
    """These feed the ``io`` on a FILE row, whose vocabulary the family fixed."""
    assert set(FILE_ACCESS.values()) == {"read", "write"}
    assert set(FCT_SERVREQ.values()) == {"read", "write"}


def test_the_no_io_kinds_are_kinds():
    assert NO_IO_KINDS <= ALL_KINDS


def test_attributes_for_is_case_insensitive_and_total():
    assert attributes_for("transaction") == attributes_for("TRANSACTION")
    # An unknown resource kind and a resource with no edges both give (), which is why the
    # caller distinguishes them with `in ATTRIBUTES` rather than by truthiness.
    assert attributes_for("NO-SUCH-RESOURCE") == ()


def test_the_payoff_edges_are_present():
    """The two rows the whole package exists for: a transaction's program, and the dataset
    behind a CICS file name."""
    txn = {a.field: a for a in attributes_for("TRANSACTION")}
    assert txn["PROGRAM"].kind == "program"
    assert txn["PROGRAM"].relation == "runs"

    fil = {a.field: a for a in attributes_for("FILE")}
    assert fil["DSNAME"].kind == "dataset"
    assert fil["DSNAME"].relation == "binds"

    # And the one people miss: a write to a TD queue starts a transaction.
    tdq = {a.field: a for a in attributes_for("TDQUEUE")}
    assert tdq["TRANSID"].kind == "cics-transaction"
    assert tdq["TRANSID"].relation == "triggers"


# --------------------------------------------------------------------------- #
# the claim about the upstream registry
# --------------------------------------------------------------------------- #

def test_the_two_registration_sets_are_disjoint():
    assert not (REGISTERED_KINDS & set(UNREGISTERED_KINDS))


@pytest.mark.parametrize("kind", sorted(REGISTERED_KINDS))
def test_the_registered_kinds_really_are_registered(kind):
    assert kind in _KIND_TYPE, (
        "resources.REGISTERED_KINDS claims %r is in mainframe_artifacts.fetch._KIND_TYPE "
        "and it is not - stage 2 would report it `skipped: no known retrieval type`"
        % kind)


@pytest.mark.parametrize("kind", sorted(UNREGISTERED_KINDS))
def test_the_unregistered_kinds_really_are_not(kind):
    """Goes RED when mainframe-common gains the entry, which is the point: that is the
    day this package should stop routing the kind to ``excluded`` and emit it as an
    artifact instead."""
    assert kind not in _KIND_TYPE, (
        "mainframe_artifacts.fetch._KIND_TYPE now knows %r - move it from "
        "UNREGISTERED_KINDS to REGISTERED_KINDS and emit it as an artifact" % kind)


@pytest.mark.parametrize("kind,rtype", sorted(UNREGISTERED_KINDS.items()))
def test_the_retrieval_type_each_unregistered_kind_wants_already_exists(kind, rtype):
    """The kinds are unregistered; the TYPES they would be fetched as are not new. If one
    of these ever fails, the upstream change is larger than adding a dict entry."""
    assert rtype in EXT_FOR_TYPE, (kind, rtype)
