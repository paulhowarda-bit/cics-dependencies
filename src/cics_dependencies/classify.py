"""What is IBM's, and must not be chased through the estate.

A CSD ships with IBM's own definitions already in it, and every application definition
points at some of them. Every one of CardDemo's eighteen transactions names
``PROFILE(DFHCICST)`` and ``TRANCLASS(DFHTCL00)``; neither is a shop artifact, neither can
be retrieved, and both would otherwise appear in the manifest as dependencies with an
honest not-found against them. Multiply by a real CSD's several hundred IBM definitions
and the handful of rows that matter are buried.

So they classify as ``ibm-runtime`` and go in ``excluded``, which is exactly what
``asm-dependencies`` does with SYS1.MACLIB macros - measured there, 78 of 106 flags in ten
modules were IBM's own names.

**The counting rule.** Excluded IBM resources are counted and reported as a total, never
dropped silently. "412 definitions, 361 of them IBM's" is a useful sentence; an
unexplained 51 is not.

**Why transactions need a list and not a prefix.** Every IBM transaction begins with ``C``.
So do ``CAUP``, ``CAVW``, ``CCLI``, ``CM00`` and thirteen more of CardDemo's - a prefix
rule would classify an entire application as IBM's and empty the manifest. The
supplied transactions are therefore enumerated, and a name not on the list is the shop's
however much it looks like CICS's.
"""

from __future__ import annotations

from typing import Optional, Tuple

from mainframe_artifacts.categories import CATEGORY_IBM

#: Module-name prefixes owned by IBM subsystems. Unlike the transaction ids these ARE safe
#: as prefixes: a shop program called DFHxxxxx would not load, because CICS's own library
#: is ahead of the application's in DFHRPL.
_IBM_PREFIXES = (
    ("DFH", "CICS itself"),
    ("DFJ", "CICS Java support"),
    ("DFE", "CICS front end programming interface"),
    ("EYU", "CICSPlex SM"),
    ("CEE", "Language Environment"),
    ("IGZ", "the COBOL runtime"),
    ("IBM", "an IBM-supplied module"),
    ("CSQ", "IBM MQ"),
    ("DSN", "Db2"),
)

#: The CICS-supplied transactions. Enumerated, for the reason in the module docstring.
_IBM_TRANSACTIONS = frozenset("""
CADP CATA CATD CATR CBAM CCIN CDBC CDBD CDBF CDBI CDBM CDBN CDBO CDBQ CDBT CDFS CDST
CEBR CECI CECS CEDA CEDB CEDC CEDF CEDX CEGN CEHP CEHS CEJR CEKL CEMN CEMT CEOT CEPD
CEPF CEPH CEPM CEPQ CEPS CEPT CESC CESD CESF CESL CESN CEST CETR CEX2 CFCL CFOR CFQR
CFQS CFTL CFTS CGRP CHLP CIDP CIEP CIND CIS1 CIS4 CISB CISC CISD CISE CISM CISQ CISR
CISS CISU CISX CITS CJGC CJLR CJPI CJSA CJSL CJSR CJSU CJTR CKAM CKBC CKBM CKBP CKBR
CKCN CKDL CKDP CKQC CKRS CKRT CKSD CKSQ CKTI CLDM CLER CLQ2 CLS1 CLS2 CLS3 CLS4 CMAC
CMPX CMSG CMTS COVR CPCT CPIA CPIH CPII CPIL CPIQ CPIR CPIS CPLT CPSS CQPI CQPO CQRY
CRDR CREA CRES CRLR CRMD CRMF CRPA CRPC CRPO CRSQ CRSR CRSY CRTE CRTP CRTX CSAC CSCY
CSFE CSFR CSFU CSGM CSGX CSHA CSHQ CSHR CSKP CSLG CSMI CSNC CSNE CSOL CSPG CSPK CSPP
CSPQ CSPS CSQC CSRK CSRS CSSF CSSY CSTE CSTP CSXM CSZI CTIN CTSD CVMI CWBA CWBC CWBG
CWTO CWWU CWXN CWXU CXCU CXRE CXRT
""".split())

#: Resource kinds whose names are transaction ids.
_TRANSACTION_KINDS = frozenset({"TRANSACTION", "cics-transaction"})


def subsystem(name: str, kind: str = "") -> Optional[Tuple[str, str]]:
    """``(category, reason)`` when ``name`` belongs to a subsystem, else ``None``.

    ``kind`` matters: ``CEMT`` is IBM's transaction and would be an ordinary program name.
    """
    if not name:
        return None
    upper = name.upper()

    if kind in _TRANSACTION_KINDS:
        if upper in _IBM_TRANSACTIONS:
            return CATEGORY_IBM, "a CICS-supplied transaction"
        # An IBM-prefixed transaction id is not a thing - all four-character CICS ids are
        # in the list above - so a DFH-prefixed name here is a shop's oddity, not IBM's.
        return None

    for prefix, owner in _IBM_PREFIXES:
        if upper.startswith(prefix):
            return CATEGORY_IBM, "supplied by %s" % owner
    return None


def is_ibm_group(group: Optional[str]) -> bool:
    """IBM's own CSD groups and lists are DFH-prefixed - ``DFHLIST``, ``DFH$SQL``.

    A whole group being IBM's is a stronger statement than a single name being IBM's: it
    means every definition inside it is CICS's own, and reporting the group is enough.
    """
    return bool(group) and group.upper().startswith("DFH")
