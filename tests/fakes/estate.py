"""A deterministic stand-in for the estate artifact service.

Answers from a fixed table so a closure test asserts what the CLOSURE did, not what some
service happened to hold. Same role as ``asm-dependencies``' ``tests/fakes/estate.py``.

The table is deliberately shaped to exercise all three answers: a member that exists, a
member that does not (the honest not-found the reports must carry), and a member whose
retrieval NAMES MORE MEMBERS - which is what makes the closure a closure rather than a
single round.
"""

from typing import Optional

#: A list the deck does not contain: GRPLIST names it, so round one asks for it. It adds a
#: group nothing has defined - which is only knowable AFTER this member has been read, and
#: is what makes round two happen.
_RPTLIST = """\
 ADD GROUP(REPORTG) LIST(RPTLIST)
"""

#: The second-round member: the group RPTLIST named and nothing had defined.
_REPORTG = """\
 DEFINE TRANSACTION(APRP) GROUP(REPORTG)
        PROGRAM(APPRPT01) STATUS(ENABLED)
 DEFINE PROGRAM(APPRPT01) GROUP(REPORTG)
        LANGUAGE(COBOL) STATUS(ENABLED)
 DEFINE FILE(RPTMAST) GROUP(REPORTG)
        DSNAME(PROD.REPORT.MASTER) READ(YES) BROWSE(YES)
"""

MEMBERS = {
    "RPTLIST": (_RPTLIST, "csd"),
    "REPORTG": (_REPORTG, "csd"),
}


def fetch_artifact(name: str, type: Optional[str] = None,  # noqa: A002 - service contract
                   copy: Optional[str] = None) -> Optional[dict]:
    """The mf-fetch contract: return the member, or None when the estate has nothing.

    ``None`` is a real answer and the reports say so - "asked and had nothing" is not the
    same as "never looked for", and this fake must be able to produce both.
    """
    hit = MEMBERS.get(str(name).strip().upper())
    if hit is None:
        return None
    text, detected = hit
    return {"text": text, "detected_type": detected, "path": "FAKE.CSD(%s)" % name}
