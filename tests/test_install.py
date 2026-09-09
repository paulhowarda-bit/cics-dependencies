"""The SIT, and the two-step closure that decides what is live."""

from cics_dependencies.classify import is_ibm_group, subsystem
from cics_dependencies.csd import parse_csd
from cics_dependencies.install import apply_install_state, installed_groups
from cics_dependencies.model import INSTALLED_NO, INSTALLED_UNKNOWN, INSTALLED_YES
from cics_dependencies.sit import parse_sit, table_members

DECK = (" DEFINE TRANSACTION(CAUP) GROUP(APPG) PROGRAM(COACTUPC)\n"
        " DEFINE FILE(OLDFILE) GROUP(DEADG) DSNAME(A.B.C)\n"
        " ADD GROUP(APPG) LIST(APPLIST)\n"
        " ADD GROUP(DEADG) LIST(OLDLIST)\n")


# --------------------------------------------------------------------------- #
# classify
# --------------------------------------------------------------------------- #

def test_ibm_prefixed_names_are_the_runtimes():
    assert subsystem("DFHCICST")[0] == "ibm-runtime"
    assert subsystem("DFHTCL00")[0] == "ibm-runtime"
    assert subsystem("EYU9XDBT")[0] == "ibm-runtime"
    assert subsystem("CEEPIPI")[0] == "ibm-runtime"


def test_an_application_name_is_not_ibms():
    assert subsystem("COACTUPC") is None
    assert subsystem("AWS.M2.CARDDEMO.ACCTDATA") is None


def test_ibm_transactions_are_a_list_because_the_prefix_would_take_the_application():
    """Every IBM transaction starts with C - and so do CAUP, CCLI and CM00. A prefix rule
    would classify a whole application as IBM's and empty the manifest."""
    assert subsystem("CEMT", "cics-transaction")[0] == "ibm-runtime"
    assert subsystem("CESN", "cics-transaction")[0] == "ibm-runtime"
    for shop in ("CAUP", "CAVW", "CCLI", "CM00", "CT01", "CU03"):
        assert subsystem(shop, "cics-transaction") is None, shop


def test_a_transaction_named_like_a_program_is_judged_as_a_transaction():
    """CEMT is IBM's transaction; the same four letters as a program name would not be."""
    assert subsystem("CEMT", "cics-transaction") is not None
    assert subsystem("CEMT", "program") is None


def test_ibm_groups_are_dfh_prefixed():
    assert is_ibm_group("DFHLIST")
    assert is_ibm_group("DFH$SQL")
    assert not is_ibm_group("CARDDEMO")
    assert not is_ibm_group(None)


# --------------------------------------------------------------------------- #
# the SIT
# --------------------------------------------------------------------------- #

def test_a_sit_macro_yields_the_grplist_and_the_identity():
    region = parse_sit(" DFHSIT TYPE=CSECT,APPLID=CICSPRDA,SYSIDNT=PRDA,\n"
                       "        GRPLIST=(APPLIST,DFHLIST),MXT=200\n")
    assert region.applid == "CICSPRDA"
    assert region.sysidnt == "PRDA"
    assert region.grplist == ["APPLIST", "DFHLIST"]


def test_a_real_column_72_continuation_resumes_at_column_16():
    """HLASM, not free text: a non-blank column 72 continues, and the next line's columns
    1-15 are the name and operation fields, not operand. Joined without stripping them, the
    first parameter of every continuation line is glued to fifteen blanks and lost."""
    first = "         DFHSIT TYPE=CSECT,APPLID=CICSPRDA,".ljust(71) + "X"
    second = "               GRPLIST=(APPLIST),MXT=200"
    region = parse_sit(first + "\n" + second + "\n")
    assert region.applid == "CICSPRDA"
    assert region.grplist == ["APPLIST"]
    assert region.sit["MXT"] == "200"


def test_parameters_that_name_nothing_are_kept_anyway():
    """MXT and DSALIM name no artifact and are frequently why the manifest was opened."""
    region = parse_sit(" DFHSIT TYPE=CSECT,MXT=200,DSALIM=5M,SEC=YES\n")
    assert region.sit["MXT"] == "200"
    assert region.sit["DSALIM"] == "5M"


def test_an_override_deck_is_read_the_same_way():
    region = parse_sit("GRPLIST=(APPLIST)\nAPPLID=CICSTST1\n.END\n")
    assert region.grplist == ["APPLIST"]
    assert region.applid == "CICSTST1"


def test_a_sit_with_no_grplist_says_so():
    region = parse_sit(" DFHSIT TYPE=CSECT,APPLID=CICSA\n")
    assert any("names no GRPLIST" in f for f in region.flags)


def test_a_source_with_no_parameters_at_all_says_so():
    region = parse_sit("this is not a SIT\n")
    assert any("no SIT parameters" in f for f in region.flags)


def test_suffix_parameters_name_members_to_retrieve():
    """PLTPI=PI means the member DFHPLTPI - the parameter carries two characters."""
    region = parse_sit(" DFHSIT TYPE=CSECT,PLTPI=PI,XLT=SD,PCT=NO,FCT=A1\n")
    members = dict((p, m) for p, m, _ in table_members(region))
    assert members["PLTPI"] == "DFHPLTPI"
    assert members["XLT"] == "DFHXLTSD"
    assert members["FCT"] == "DFHFCTA1"
    assert "PCT" not in members          # PCT=NO means there is no PCT


# --------------------------------------------------------------------------- #
# the closure
# --------------------------------------------------------------------------- #

def test_a_group_reached_from_grplist_is_installed():
    region = parse_csd(DECK)
    parse_sit(" DFHSIT TYPE=CSECT,GRPLIST=(APPLIST)\n", region=region)
    apply_install_state(region)
    states = {r.name: r.installed for r in region.resources}
    assert states == {"CAUP": INSTALLED_YES, "OLDFILE": INSTALLED_NO}


def test_the_orphan_count_is_reported_with_the_runtime_caveat():
    region = parse_csd(DECK)
    parse_sit(" DFHSIT TYPE=CSECT,GRPLIST=(APPLIST)\n", region=region)
    apply_install_state(region)
    orphan = next(f for f in region.flags if "in no group that GRPLIST reaches" in f)
    assert "1 of 2" in orphan
    assert "CEDA INSTALL" in orphan


def test_without_a_sit_everything_stays_unknown_and_one_flag_says_why():
    region = apply_install_state(parse_csd(DECK))
    assert {r.installed for r in region.resources} == {INSTALLED_UNKNOWN}
    assert sum("installed: unknown" in f for f in region.flags) == 1


def test_a_list_named_by_grplist_but_not_in_hand_is_reported_with_its_cost():
    region = parse_csd(DECK)
    parse_sit(" DFHSIT TYPE=CSECT,GRPLIST=(APPLIST,MISSING)\n", region=region)
    _, flags = installed_groups(region)
    assert any("MISSING" in f and "unaccounted for" in f for f in flags)


def test_a_missing_ibm_list_is_reported_more_narrowly():
    """DFHLIST is in every real GRPLIST and holds CICS's own definitions. Reporting it the
    same way as a missing application list would send a reader looking for shop resources
    that were never there."""
    region = parse_csd(DECK)
    parse_sit(" DFHSIT TYPE=CSECT,GRPLIST=(APPLIST,DFHLIST)\n", region=region)
    _, flags = installed_groups(region)
    ibm = next(f for f in flags if "DFHLIST" in f)
    assert "CICS's own definitions" in ibm
    assert "unaccounted for" not in ibm


def test_the_closure_is_idempotent():
    region = parse_csd(DECK)
    parse_sit(" DFHSIT TYPE=CSECT,GRPLIST=(APPLIST)\n", region=region)
    first = {r.name: apply_install_state(region).resources[i].installed
             for i, r in enumerate(region.resources)}
    second = {r.name: apply_install_state(region).resources[i].installed
              for i, r in enumerate(region.resources)}
    assert first == second
