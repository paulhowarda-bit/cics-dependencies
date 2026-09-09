"""The CSD lexer, on the cases real decks actually contain."""

from cics_dependencies.lexer import lex_csd


def _ops(statement):
    return [(op.keyword, op.value) for op in statement.operands]


def test_a_statement_continues_until_the_next_command():
    stmts, flags = lex_csd(
        " DEFINE FILE(ACCTDAT) GROUP(CARDDEMO)\n"
        "        DSNAME(AWS.M2.ACCTDATA) STATUS(ENABLED)\n"
        " DEFINE FILE(CUSTDAT) GROUP(CARDDEMO)\n")
    assert [s.verb for s in stmts] == ["DEFINE", "DEFINE"]
    assert stmts[0].first("DSNAME") == "AWS.M2.ACCTDATA"
    assert stmts[1].first("FILE") == "CUSTDAT"
    assert flags == []


def test_indentation_is_not_the_continuation_signal():
    """DESCRIPTION sits in column 2, the same column DEFINE sits in. A lexer that
    continued on indentation would make it a statement of its own and lose it."""
    stmts, _ = lex_csd(
        " DEFINE MAPSET(COACTUP) GROUP(CARDDEMO)\n"
        " DESCRIPTION(CREDIT CARD ACCOUNT UPDATE MAP)\n"
        "        RESIDENT(NO)\n")
    assert len(stmts) == 1
    assert stmts[0].first("DESCRIPTION") == "CREDIT CARD ACCOUNT UPDATE MAP"


def test_a_value_may_contain_blanks_and_commas():
    """Both are real: DEFINETIME(22/06/10 20:03:53) and WAITTIME(0,0,0). Splitting
    operands on whitespace truncates the first; splitting on commas shatters the second."""
    stmts, _ = lex_csd(" DEFINE TRANSACTION(CAUP) WAITTIME(0,0,0)\n"
                       "        DEFINETIME(22/06/10 20:03:53)\n")
    assert stmts[0].first("WAITTIME") == "0,0,0"
    assert stmts[0].first("DEFINETIME") == "22/06/10 20:03:53"


def test_a_command_verb_followed_by_a_paren_is_an_operand():
    """ADD, DELETE and LIST are DFHCSDUP commands AND ordinary FILE attributes. Without
    this rule a continuation line beginning DELETE(YES) silently becomes a DELETE command
    and every attribute after it lands on the wrong statement."""
    stmts, _ = lex_csd(" DEFINE FILE(ACCTDAT) GROUP(CARDDEMO)\n"
                       "        ADD(YES) DELETE(YES) READ(YES)\n"
                       "        BROWSE(YES) UPDATE(YES)\n")
    assert len(stmts) == 1
    assert stmts[0].first("ADD") == "YES"
    assert stmts[0].first("DELETE") == "YES"


def test_a_command_verb_not_followed_by_a_paren_starts_a_statement():
    stmts, _ = lex_csd(" DEFINE FILE(X) GROUP(G)\n"
                       " ADD GROUP(G) LIST(L)\n")
    assert [s.verb for s in stmts] == ["DEFINE", "ADD"]
    assert _ops(stmts[1]) == [("GROUP", "G"), ("LIST", "L")]


def test_a_bare_keyword_keeps_a_none_value():
    """DELETE GROUP(CARDDEMO) ALL - the ALL is not decoration, it changes the command."""
    stmts, _ = lex_csd(" DELETE GROUP(CARDDEMO) ALL\n")
    assert _ops(stmts[0]) == [("GROUP", "CARDDEMO"), ("ALL", None)]


def test_operands_report_their_own_line_not_the_statements():
    stmts, _ = lex_csd(" DEFINE TRANSACTION(CAUP) GROUP(CARDDEMO)\n"
                       "        PROGRAM(COACTUPC)\n"
                       "        TRANCLASS(DFHTCL00)\n")
    lines = {op.keyword: op.line for op in stmts[0].operands}
    assert lines["TRANSACTION"] == 1
    assert lines["PROGRAM"] == 2
    assert lines["TRANCLASS"] == 3


def test_comments_and_blank_lines_are_skipped():
    stmts, flags = lex_csd("*** a banner\n"
                           "\n"
                           " DEFINE FILE(X) GROUP(G)\n"
                           "*\n")
    assert len(stmts) == 1
    assert flags == []


def test_content_past_column_72_is_reported_not_dropped_silently():
    long = " DEFINE FILE(X) GROUP(G)" + " " * 50 + "STATUS(ENABLED)"
    stmts, flags = lex_csd(long + "\n")
    assert stmts[0].first("STATUS") is None
    assert any("past column 72" in f for f in flags)


def test_a_sequence_field_past_column_72_is_not_flagged():
    line = (" DEFINE FILE(X) GROUP(G)".ljust(72) + "00000100")
    _, flags = lex_csd(line + "\n")
    assert flags == []


def test_an_unclosed_parenthesis_is_flagged_on_the_statement():
    stmts, _ = lex_csd(" DEFINE FILE(ACCTDAT GROUP(CARDDEMO)\n")
    assert any("never closed" in f for f in stmts[0].flags)


def test_text_before_the_first_command_is_reported():
    _, flags = lex_csd("garbage\n DEFINE FILE(X) GROUP(G)\n")
    assert any("before the first command" in f for f in flags)


def test_lower_case_is_accepted_and_normalised():
    """IBM's own sample deck is written in mixed case."""
    stmts, _ = lex_csd(" Define Transaction(HCAZ) Group(HCAZMOBL)\n"
                       "        Program(HCAZMENU) TaskDataLoc(Any)\n")
    assert stmts[0].verb == "DEFINE"
    assert stmts[0].first("TRANSACTION") == "HCAZ"
    assert stmts[0].first("PROGRAM") == "HCAZMENU"
