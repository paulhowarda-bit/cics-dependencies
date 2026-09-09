"""THE TABLE: which attribute of which CICS resource definition names which artifact.

Pure data. No parsing, no I/O, no judgement about whether a name resolves - just the
statement that ``DEFINE TRANSACTION(...) PROGRAM(x)`` makes ``x`` a ``program`` this
transaction runs, and that ``DFHPCT TYPE=ENTRY,PROGRAM=x`` says the same thing in the
older syntax.

Kept here, in one table, for two reasons.

**A reader can see the whole edge set at once.** In a declarative resource definition the
attribute keyword IS the evidence, so the edge set is not emergent behaviour of a parser -
it is a list, and a list belongs somewhere it can be read as a list.

**The parsers read it rather than restating it.** ``csd.py`` and ``tables.py`` consume the
same rows, which is what makes a 1974 ``DFHPCT`` deck and a 2019 ``DEFINE TRANSACTION``
produce an identical manifest row. An attribute handled in a parser but missing from this
table produces a silently missing edge with no flag, and that is the exact failure this
family of tools exists to avoid.

What is deliberately NOT here: the many attributes that name no artifact (``TWASIZE``,
``PRIORITY``, ``DTIMOUT``, ``SCRNSIZE``, ``MAXACTIVE``, ...). They are carried on the
resource as plain attributes and reported, but they are not edges.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

# --------------------------------------------------------------------------- #
# the kind vocabulary
# --------------------------------------------------------------------------- #

#: Artifact kinds this package emits that are ALREADY registered in
#: ``mainframe_artifacts.fetch._KIND_TYPE``, so stage 2 can request them.
REGISTERED_KINDS = frozenset({
    "program", "file", "dataset", "queue", "terminal-map", "cics-transaction",
    "db2-table", "copybook", "macro",
})

#: Kinds this package needs that are NOT yet registered upstream. Emitting one as an
#: artifact would have stage 2 report ``skipped: no known retrieval type``, which is
#: false - a CSD-defined resource is retrievable, as ``csd``, the same way
#: ``cics-transaction`` already is. Until mainframe-common gains the entries these go in
#: ``excluded`` with the reason, which is the pattern asm-dependencies uses for ``psb``
#: and ``segment``.
#:
#: The value is the retrieval type each SHOULD get upstream.
UNREGISTERED_KINDS: Dict[str, str] = {
    "cics-group":         "csd",
    "cics-list":          "csd",
    "cics-profile":       "csd",
    "cics-tranclass":     "csd",
    "cics-connection":    "csd",
    "cics-urimap":        "csd",
    "cics-tcpipservice":  "csd",
    "cics-pipeline":      "csd",
    "cics-webservice":    "csd",
    "cics-library":       "csd",
    "cics-lsrpool":       "csd",
    "cics-journalmodel":  "csd",
    "cics-jvmserver":     "csd",
    "cics-bundle":        "csd",
    "cics-partitionset":  "csd",
    "cics-processtype":   "csd",
    "cics-doctemplate":   "csd",
    "cics-typeterm":      "csd",
    "cics-terminal":      "csd",
    "cics-db2entry":      "csd",
    "cics-region":        "jcl",
    "db2-plan":           "ddl",
}

ALL_KINDS = REGISTERED_KINDS | frozenset(UNREGISTERED_KINDS)


# --------------------------------------------------------------------------- #
# one edge
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Attr:
    """One attribute of one resource kind that names another artifact.

    ``field``    the CSD keyword, as written in a ``DEFINE``.
    ``kind``     the artifact kind its value names.
    ``relation`` what the edge MEANS, in one word. Not decoration: ``runs`` and
                 ``triggers`` are both TRANSACTION edges and a graph loader that
                 conflates them cannot tell a menu from a queue-driven batch task.
    ``macro``    the operand that spells the same thing in the macro-table era, when it
                 differs from ``field``. ``None`` means the same spelling; absent from
                 ``MACRO_RESOURCE`` for that kind means the era had no equivalent.
    ``note``     why the edge exists, for the row's ``needs`` text.
    """

    field: str
    kind: str
    relation: str
    macro: Optional[str] = None
    note: str = ""

    def macro_field(self) -> str:
        """The operand name in the macro-table era."""
        return self.macro or self.field


# --------------------------------------------------------------------------- #
# the table
# --------------------------------------------------------------------------- #

#: resource kind -> the attributes of it that name another artifact.
#:
#: Keyed by the CSD resource type, in upper case, exactly as a ``DEFINE`` spells it. The
#: macro-table parsers reach the same rows through ``MACRO_RESOURCE``.
ATTRIBUTES: Dict[str, Tuple[Attr, ...]] = {

    "TRANSACTION": (
        Attr("PROGRAM", "program", "runs",
             note="the first program the transaction dispatches"),
        Attr("PROFILE", "cics-profile", "profiled-by"),
        Attr("TRANCLASS", "cics-tranclass", "classified-by"),
        Attr("PARTITIONSET", "cics-partitionset", "uses"),
        Attr("BREXIT", "program", "uses",
             note="the 3270 bridge exit program"),
        Attr("REMOTESYSTEM", "cics-connection", "routed-to",
             note="the transaction runs in ANOTHER region; the program named here, if "
                  "any, is not the one that runs"),
        Attr("TASKREQ", "cics-terminal", "started-by",
             note="a terminal key or PA/PF request that starts this transaction"),
    ),

    "PROGRAM": (
        Attr("REMOTESYSTEM", "cics-connection", "routed-to"),
        Attr("TRANSID", "cics-transaction", "routed-as",
             note="the transaction a dynamically routed link runs under"),
        Attr("JVMSERVER", "cics-jvmserver", "runs-in"),
    ),

    "MAPSET": (
        # The mapset IS a load module; its BMS source and its symbolic-map copybook are
        # separate members, and bms.py joins them.
        Attr("RESIDENT", "terminal-map", "self",
             note="placeholder: MAPSET names no other artifact by attribute - the edge "
                  "to BMS source is by name, established in bms.py"),
    ),

    "FILE": (
        Attr("DSNAME", "dataset", "binds",
             note="THE edge: unlike a batch ddname, a CICS file is bound to its VSAM "
                  "dataset here rather than in JCL. A macro-era FCT usually omits it, "
                  "and the binding is then a DD on the DFHSIP step"),
        Attr("LSRPOOLNUM", "cics-lsrpool", "buffers-in", macro="LSRPOOL"),
        Attr("JOURNAL", "cics-journalmodel", "logs-to"),
        Attr("REMOTESYSTEM", "cics-connection", "routed-to"),
    ),

    "TDQUEUE": (
        Attr("TRANSID", "cics-transaction", "triggers",
             note="with TRIGGERLEVEL: a write to this queue STARTS that transaction. "
                  "The write can come from a batch job through the extrapartition "
                  "dataset, which is how a batch job starts online work"),
        # A DDNAME is NOT a dataset - it is the name of a DD statement on the region
        # startup job, and what it points at is in that JCL. Emitting it as `dataset`
        # produced rows like `dataset INREADER`, which reads as a catalogued dataset
        # called INREADER and joins to nothing. `file` is the family's kind for a name
        # awaiting a dataset, exactly as the COBOL and assembler sides use it for a
        # ddname; bind_jcl_region turns it into a real dataset.
        # The macro era spells the same thing DSCNAME - the symbolic name of the data set
        # control block, which is a DD name, not a dataset.
        Attr("DDNAME", "file", "writes-through", macro="DSCNAME",
             note="extrapartition: the DD on the CICS region startup JCL says which "
                  "dataset this is - supply that job to bind_jcl_region to resolve it"),
        Attr("DSNAME", "dataset", "binds",
             note="CSD-only: a TDQUEUE may name its dataset directly for dynamic "
                  "allocation. A macro-era DCT never does - it has DSCNAME instead"),
        Attr("INDIRECTNAME", "queue", "redirects-to", macro="INDDEST"),
        Attr("REMOTESYSTEM", "cics-connection", "routed-to"),
        Attr("FACILITYID", "cics-terminal", "started-at"),
    ),

    "TSMODEL": (
        Attr("PREFIX", "queue", "models",
             note="matches a queue name by PREFIX, not by equality - a program's "
                  "WRITEQ TS QUEUE('CUSTWRK1') joins to it as a prefix match and the "
                  "row says so"),
        Attr("POOLNAME", "dataset", "stored-in",
             note="a shared TS pool lives outside this region"),
        Attr("REMOTESYSTEM", "cics-connection", "routed-to"),
    ),

    "DB2ENTRY": (
        Attr("TRANSID", "cics-transaction", "serves", macro="TXID"),
        Attr("PLAN", "db2-plan", "binds"),
        Attr("PLANEXITNAME", "program", "uses", macro="PLNPGME"),
    ),

    "DB2TRAN": (
        Attr("ENTRY", "cics-db2entry", "extends",
             note="attaches further transactions to a DB2ENTRY's plan"),
        Attr("TRANSID", "cics-transaction", "serves"),
    ),

    "LIBRARY": (
        # DSNAME01..DSNAME16 - the parser expands the numbered form and emits one row per
        # populated slot, in RANKING then slot order, because the ORDER is the search
        # order and a set loses it.
        Attr("DSNAME", "dataset", "loads-from",
             note="a DFHRPL-equivalent concatenation; the slot order is the load-module "
                  "search order"),
    ),

    "URIMAP": (
        Attr("TRANSACTION", "cics-transaction", "starts"),
        Attr("PROGRAM", "program", "runs"),
        Attr("PIPELINE", "cics-pipeline", "uses"),
        Attr("WEBSERVICE", "cics-webservice", "uses"),
        Attr("TCPIPSERVICE", "cics-tcpipservice", "listens-on"),
        Attr("TEMPLATENAME", "cics-doctemplate", "serves"),
    ),

    "TCPIPSERVICE": (
        Attr("TRANSACTION", "cics-transaction", "starts",
             note="the attach transaction for an inbound connection"),
        Attr("URM", "program", "uses",
             note="the user-replaceable analyzer program"),
    ),

    "PIPELINE": (
        Attr("CONFIGFILE", "dataset", "configured-by", note="a zFS path, not a member"),
        Attr("WSDIR", "dataset", "scans", note="a zFS pickup directory"),
        Attr("SHELF", "dataset", "uses"),
    ),

    "WEBSERVICE": (
        Attr("PIPELINE", "cics-pipeline", "uses"),
        Attr("PROGRAM", "program", "runs"),
        Attr("WSBIND", "dataset", "bound-by", note="a zFS path"),
        Attr("WSDLFILE", "dataset", "described-by", note="a zFS path"),
    ),

    "CONNECTION": (
        Attr("NETNAME", "cics-region", "connects-to"),
        Attr("REMOTESYSTEM", "cics-region", "connects-to"),
    ),

    "IPCONN": (
        Attr("APPLID", "cics-region", "connects-to"),
        Attr("TCPIPSERVICE", "cics-tcpipservice", "listens-on"),
    ),

    "SESSIONS": (
        Attr("CONNECTION", "cics-connection", "belongs-to"),
        Attr("PROFILE", "cics-profile", "profiled-by"),
    ),

    "TERMINAL": (
        Attr("TYPETERM", "cics-typeterm", "typed-by"),
        Attr("TRANSACTION", "cics-transaction", "starts",
             note="the transaction started automatically at this terminal"),
        Attr("PRINTER", "cics-terminal", "prints-to"),
        Attr("ALTPRINTER", "cics-terminal", "prints-to"),
    ),

    "PROFILE": (
        Attr("JOURNAL", "cics-journalmodel", "logs-to"),
    ),

    "JOURNALMODEL": (
        Attr("STREAMNAME", "dataset", "writes-to",
             note="an MVS log stream, not a dataset in the catalog sense"),
    ),

    "PROCESSTYPE": (
        Attr("FILE", "file", "stores-in"),
        Attr("AUDITLOG", "cics-journalmodel", "logs-to"),
    ),

    "DOCTEMPLATE": (
        Attr("FILE", "file", "reads-from"),
        Attr("TSQUEUE", "queue", "reads-from"),
        Attr("TDQUEUE", "queue", "reads-from"),
        Attr("PROGRAM", "program", "generated-by"),
        Attr("DDNAME", "dataset", "reads-from"),
        Attr("MEMBER", "copybook", "reads-from",
             note="a member of the DDNAME library"),
    ),

    "MQMONITOR": (
        Attr("TRANSACTION", "cics-transaction", "triggers",
             note="an MQ message on QNAME starts this transaction"),
    ),

    "ATOMSERVICE": (
        Attr("BINDFILE", "dataset", "bound-by"),
        Attr("CONFIGFILE", "dataset", "configured-by"),
        Attr("RESOURCENAME", "file", "serves"),
    ),

    "BUNDLE": (
        Attr("BUNDLEDIR", "cics-bundle", "defined-by",
             note="a zFS directory whose META-INF/cics.xml defines further resources - "
                  "a second definition source, not a leaf"),
    ),

    "JVMSERVER": (
        Attr("JVMPROFILE", "dataset", "configured-by"),
    ),

    "ENQMODEL": (
        Attr("ENQNAME", "queue", "serialises",
             note="an ENQ name is a string, not a stored artifact; reported for the "
                  "cross-region serialisation it implies"),
    ),
}


# --------------------------------------------------------------------------- #
# the macro-table era
# --------------------------------------------------------------------------- #

#: Table macro -> the CSD resource kind its entries define. The macro parsers use this to
#: reach the SAME rows in ``ATTRIBUTES``, which is what makes both eras produce one
#: manifest shape.
#:
#: ``DFHPPT`` is two kinds: an entry carries either ``PROGRAM=`` or ``MAPSET=``, so the
#: parser picks by which operand is present rather than by the macro name.
MACRO_RESOURCE: Dict[str, str] = {
    "DFHPCT":  "TRANSACTION",
    "DFHPPT":  "PROGRAM",       # or MAPSET - decided per entry
    "DFHFCT":  "FILE",
    "DFHDCT":  "TDQUEUE",
    "DFHTST":  "TSMODEL",
    "DFHTCT":  "TERMINAL",
    "DSNCRCT": "DB2ENTRY",
}

#: Macro-name PREFIXES that mean the same tables. ``DFH`` is IBM's; ``KIK`` is KICKS, the
#: CICS-compatible system, whose PCT/PPT/FCT decks are ``KIKPCT``/``KIKPPT``/``KIKFCT`` and
#: are otherwise identical in shape - which is how this was found, in KICKS's own tables.
#:
#: A shop that wraps the IBM macros in its own is the same problem one step further on, and
#: is why this is a list rather than a hard-coded ``DFH``: add the site's prefix and the
#: decks parse. What CANNOT be handled this way is a site macro with a different OPERAND
#: vocabulary, and that is flagged rather than guessed.
MACRO_PREFIXES = ("DFH", "KIK")


def macro_family(operation: str) -> Optional[str]:
    """The IBM macro this operation is a spelling of, or None.

    ``KIKPCT`` -> ``DFHPCT``. Exact IBM names pass through unchanged, and anything whose
    stem is not a known table returns None rather than being force-fitted.
    """
    upper = operation.upper()
    if upper in MACRO_RESOURCE or upper in MACRO_LISTS:
        return upper
    for prefix in MACRO_PREFIXES:
        if upper.startswith(prefix):
            candidate = "DFH" + upper[len(prefix):]
            if candidate in MACRO_RESOURCE or candidate in MACRO_LISTS:
                return candidate
    return None

#: Macros that define a LIST of things rather than a resource with attributes. Each entry
#: is one edge and nothing else.
MACRO_LISTS: Dict[str, Tuple[str, str, str]] = {
    # macro    -> (operand, kind, relation)
    "DFHPLT": ("PROGRAM", "program", "runs-at-startup-or-shutdown"),
    "DFHXLT": ("TRANSID", "cics-transaction", "allowed-at-shutdown"),
}


# --------------------------------------------------------------------------- #
# permitted access
# --------------------------------------------------------------------------- #

#: CSD FILE attributes that grant an access, and what each grants. This is what the region
#: PERMITS, never what a program does - the observed access comes from a program manifest
#: through ``views.bind_program_artifacts``. Collapsing the two makes every read-only file
#: look updated.
FILE_ACCESS: Dict[str, str] = {
    "READ": "read", "BROWSE": "read",
    "ADD": "write", "UPDATE": "write", "DELETE": "write",
}

#: The macro era spells the same thing as one operand with a value list.
FCT_SERVREQ: Dict[str, str] = {
    "GET": "read", "BROWSE": "read",
    "PUT": "write", "ADD": "write", "UPDATE": "write", "DELETE": "write",
    "NEWREC": "write",
}


# --------------------------------------------------------------------------- #
# resources whose identity is not a name
# --------------------------------------------------------------------------- #

#: Kinds that carry NO ``io`` on their manifest row, whatever the source said. House rule
#: across the family: SEND and RECEIVE describe a conversation, not a direction of access
#: to a load module, and giving them an ``io`` makes a consumer's ``io`` rule mean two
#: different things.
NO_IO_KINDS = frozenset({
    "program", "cics-transaction", "terminal-map", "cics-profile", "cics-tranclass",
    "cics-connection", "cics-region", "cics-group", "cics-list", "cics-partitionset",
    "cics-typeterm", "cics-terminal", "cics-jvmserver", "cics-db2entry", "db2-plan",
    "macro", "copybook",
})


#: What a defined resource of each type IS, as a manifest kind. This is what goes in
#: ``provides``, and what a peer's unresolved row joins to: a COBOL manifest's
#: ``cics-transaction`` row for ``MENU`` matches a ``DEFINE TRANSACTION(MENU)`` here.
#:
#: A CSD resource type absent from this mapping is one this package does not model. It is
#: flagged by name rather than dropped, because a deck full of resource types the parser
#: skipped silently reads as a small deck.
PROVIDES_KIND: Dict[str, str] = {
    "TRANSACTION":  "cics-transaction",
    "PROGRAM":      "program",
    "MAPSET":       "terminal-map",
    "PARTITIONSET": "cics-partitionset",
    "FILE":         "file",
    "TDQUEUE":      "queue",
    "TSMODEL":      "queue",
    "LIBRARY":      "cics-library",
    "PROFILE":      "cics-profile",
    "TRANCLASS":    "cics-tranclass",
    "LSRPOOL":      "cics-lsrpool",
    "JOURNALMODEL": "cics-journalmodel",
    "CONNECTION":   "cics-connection",
    "IPCONN":       "cics-connection",
    "SESSIONS":     "cics-connection",
    "TERMINAL":     "cics-terminal",
    "TYPETERM":     "cics-typeterm",
    "URIMAP":       "cics-urimap",
    "TCPIPSERVICE": "cics-tcpipservice",
    "PIPELINE":     "cics-pipeline",
    "WEBSERVICE":   "cics-webservice",
    "DB2ENTRY":     "cics-db2entry",
    "DB2TRAN":      "cics-db2entry",
    "JVMSERVER":    "cics-jvmserver",
    "BUNDLE":       "cics-bundle",
    "PROCESSTYPE":  "cics-processtype",
    "DOCTEMPLATE":  "cics-doctemplate",
}

#: Every resource type a ``DEFINE`` may name. Wider than ``PROVIDES_KIND`` on purpose:
#: these are recognised as valid definitions even where the manifest has no kind for them
#: yet, so an unrecognised type means "not a CICS resource type", not "not modelled".
RESOURCE_TYPES = frozenset(PROVIDES_KIND) | frozenset({
    "ATOMSERVICE", "AUTINSTMODEL", "CORBASERVER", "DB2CONN", "DJAR", "ENQMODEL",
    "MQCONN", "MQMONITOR", "PARTNER", "REQUESTMODEL", "TRANSACTION", "TDQUEUE",
})

#: Attribute values that mean "no such resource" rather than naming one. Real decks are
#: full of ``JOURNAL(NO)`` and ``REMOTESYSTEM(NONE)``, and an edge built from either is an
#: artifact named "NO" - a row that is not merely useless but actively wrong, since it
#: joins to nothing and reads as a dependency the program has.
NON_NAMES = frozenset({"", "NO", "NONE"})


def permitted_io(attributes: Dict[str, str]) -> Optional[str]:
    """The access a FILE definition PERMITS, in either era's spelling.

    The CSD says ``READ(YES) UPDATE(YES) ...``; a ``DFHFCT`` entry says
    ``SERVREQ=(GET,PUT,BROWSE)``. Both are read here, because both parsers AND
    ``bind_jcl_region`` need the answer and none of them should own it - a JCL-bound
    macro-era file whose SERVREQ was never consulted would come back with a dataset and no
    permitted access at all.

    Not what any program does with it: a CSD file is defined with all five of
    ``READ/UPDATE/ADD/DELETE/BROWSE`` far more often than any program uses them.
    """
    grants = {FILE_ACCESS[k] for k, v in attributes.items()
              if k in FILE_ACCESS and v.strip().upper() == "YES"}
    servreq = attributes.get("SERVREQ")
    if servreq:
        for request in servreq.strip().strip("()").split(","):
            grant = FCT_SERVREQ.get(request.strip().upper())
            if grant:
                grants.add(grant)
    if not grants:
        return None
    return "read-write" if len(grants) > 1 else next(iter(grants))


def attributes_for(resource_kind: str) -> Tuple[Attr, ...]:
    """The edge-bearing attributes of ``resource_kind``, or an empty tuple.

    An empty tuple is a real answer - TRANCLASS and LSRPOOL name nothing - and is not the
    same as an unknown resource kind, which the caller checks with ``resource_kind in
    ATTRIBUTES``.
    """
    return ATTRIBUTES.get(resource_kind.upper(), ())
