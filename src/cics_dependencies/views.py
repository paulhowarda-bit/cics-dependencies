"""Region -> the JSON views, in the same shape as the rest of the family.

``build_cics_artifacts(region)`` is the manifest: ``provides`` (every resource these
sources DEFINE, which is the half a peer's unresolved CICS rows join to) and ``artifacts``
(one row per artifact the definitions NAME), plus ``excluded`` and ``flags``.

Two things here are this package's own, and both come from the two-eras decision:

**A conflict is reported, never resolved.** When two sources define the same resource
differently - a `DFHPCT` deck says `MENU` runs `MENU001` and the CSD says `MENU009` - both
rows stand, each carrying its era, and a flag names the conflict. A stale deck in a PDS is
textually identical to a live one.

**Every row carries `installed` beside its `evidence`.** They answer different questions,
and the case that occurs most is a perfectly known definition in a group nothing installs.

The binders (``bind_program_artifacts``, ``bind_jcl_region``) are not written yet - see
CLAUDE.md's build order. They take plain dicts and return plain dicts, so this package
never imports a peer.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from mainframe_artifacts.categories import CATEGORY_IBM

from . import PROGRAM_BINDING_API_VERSION
from .classify import is_ibm_group, subsystem
from .csd import provides
from .model import EVIDENCE_LITERAL, INSTALLED_YES, Reference, Region, Resource
from .resources import (NO_IO_KINDS, PROVIDES_KIND, REGISTERED_KINDS, UNREGISTERED_KINDS,
                        permitted_io)

FORMAT_ARTIFACTS = "cics-dependencies-artifacts"
FORMAT_LINEAGE = "cics-dependencies-lineage"

#: Relations that START work in the region. Driven off the relation rather than off a list
#: of resource types, so a new entry-point kind added to ``resources.ATTRIBUTES`` with the
#: right relation appears here without this module being touched.
_STARTS = frozenset({"starts", "triggers"})

#: Emission order for the manifest. An unknown kind sorts last rather than crashing.
_CLASS_ORDER = {
    "program": 0, "cics-transaction": 1, "file": 2, "dataset": 3, "terminal-map": 4,
    "queue": 5, "db2-plan": 6,
}

_ARTIFACTS_NOTE = (
    "One row per artifact these CICS resource definitions NAME: the programs transactions "
    "run, the datasets file definitions bind, the transactions a queue write triggers, the "
    "libraries load modules come from. `provides` is the other half - every resource these "
    "sources DEFINE - and it is what a COBOL or assembler manifest's unresolved "
    "cics-transaction, file, queue and terminal-map rows join to. Every row carries "
    "`installed` as well as `evidence`: how well the name is known and whether the "
    "definition is live are different questions. A file row's `io` is the access the "
    "region PERMITS, not the access any program makes.")

#: A file definition grants access; a program makes it. Said on the row so a consumer
#: cannot read one as the other.
_PERMITTED = "permitted by the definition, not observed in any program"

#: Peer-manifest row kinds this package can resolve. Anything else in their manifest -
#: copybooks, Db2 tables, batch datasets - is none of this package's business and is
#: passed through untouched.
_BINDABLE = frozenset({"cics-transaction", "file", "queue", "terminal-map", "program"})

_UNBOUND_DEFAULT = "no definition of this name is in these sources"
_UNBOUND_REASON = {
    "terminal-map": "no MAPSET of this name is defined here. Often correct rather than a "
                    "gap: a program names both the MAPSET and the MAP inside it, and only "
                    "the mapset is ever a CSD resource - the map is in the BMS source",
    "file": "no FILE definition of this name is in these sources, so the VSAM dataset "
            "behind it is unknown. Either the group holding it was not supplied, or the "
            "region defines it in a macro-era FCT",
    "queue": "no TDQUEUE of this name, and no TSMODEL whose PREFIX it starts with. A TS "
             "queue with no model is legal - it just takes the region's defaults",
    "cics-transaction": "no TRANSACTION definition of this name is in these sources, so "
                        "which program it runs is unknown here",
    "program": "no PROGRAM definition of this name is in these sources. Under AUTOINSTALL "
               "that is normal - the definition is created at first use and never "
               "written down",
}


def _identity(kind: str) -> Tuple[Optional[str], str]:
    """``(resolvedBy, needs)`` - what would settle this row's identity, and who says so."""
    if kind == "dataset":
        return ("the catalog", "nothing further - a fully qualified dataset name is the "
                                "estate-wide identity")
    if kind == "program":
        return ("the load module in a LIBRARY or DFHRPL concatenation",
                "which library supplies it, which is the LIBRARY definitions' ranking "
                "order rather than anything in this definition")
    if kind == "cics-transaction":
        return ("the TRANSACTION definition", "the definition that says which program it "
                                              "runs - in these sources if it is here")
    return (None, "the definition that declares it")


def _excluded_reason(kind: str, name: str) -> Optional[Dict[str, str]]:
    """Why a named artifact does not become a manifest row, or None if it should."""
    ibm = subsystem(name, kind)
    if ibm is not None:
        return {"category": ibm[0], "reason": ibm[1]}
    if kind in UNREGISTERED_KINDS:
        return {"category": "not-retrievable-yet",
                "reason": "'%s' has no entry in mainframe_artifacts.fetch._KIND_TYPE, so "
                          "stage 2 would report it `skipped: no known retrieval type` - "
                          "which is false, since it would be retrievable as '%s'"
                          % (kind, UNREGISTERED_KINDS[kind])}
    if kind not in REGISTERED_KINDS:
        return {"category": "not-modelled",
                "reason": "'%s' is not a kind this package emits" % kind}
    return None


def _touch(resource: Resource, reference) -> dict:
    return {"resource": resource.name, "resourceType": resource.kind,
            "group": resource.group, "field": reference.field,
            "relation": reference.relation, "line": reference.line}


def _conflicts(region: Region) -> List[str]:
    """One flag per resource defined more than once, whether or not the eras differ.

    Same-name definitions in two groups of one CSD are as real as a CSD/macro conflict and
    are just as capable of sending a reader to the wrong program.
    """
    seen: Dict[Tuple[str, str], List[Resource]] = {}
    for res in region.resources:
        seen.setdefault((PROVIDES_KIND.get(res.kind, res.kind), res.name), []).append(res)

    flags: List[str] = []
    for (_kind, name), group in sorted(seen.items()):
        if len(group) < 2:
            continue
        where = "; ".join("%s line %d (%s, group %s)"
                          % (r.source_name, r.line or 0, r.source, r.group or "none")
                          for r in group)
        flags.append(
            "%s %s is defined %d times and neither definition is preferred: %s. Which is "
            "live is decided by the SIT, not by this text - a stale deck reads exactly "
            "like a current one" % (group[0].kind, name, len(group), where))
    return flags


def build_cics_artifacts(region: Region) -> dict:
    """The manifest: one row per artifact these definitions name, deduplicated."""
    rows: Dict[Tuple[str, str], dict] = {}
    excluded: Dict[Tuple[str, str], dict] = {}
    provided = provides(region)
    # (kind, name) -> where it is defined. A transaction named by a PROGRAM's TRANSID is
    # very often defined in the same deck, and a row that does not say so sends stage 2 to
    # the estate for something already in hand. It is still an artifact - the edge is
    # real - so it is annotated, not excluded.
    defined_here = {(row["kind"], row["name"]): row for row in provided}

    for res in region.resources:
        group_is_ibm = is_ibm_group(res.group)
        for ref in res.references:
            key = (ref.kind, ref.name)
            reason = _excluded_reason(ref.kind, ref.name)
            if reason is None and group_is_ibm:
                reason = {"category": CATEGORY_IBM,
                          "reason": "defined in the IBM-supplied group %s" % res.group}
            if reason is not None:
                row = excluded.setdefault(key, {
                    "name": ref.name, "kind": ref.kind, "category": reason["category"],
                    "reason": reason["reason"], "touchedBy": []})
                row["touchedBy"].append(_touch(res, ref))
                continue

            row = rows.get(key)
            if row is None:
                resolved_by, needs = _identity(ref.kind)
                row = rows[key] = {
                    "artifact": ref.name,
                    "kind": ref.kind,
                    "dependency": "runtime",
                    "relation": ref.relation,
                    "evidence": ref.evidence,
                    "installed": res.installed,
                    "resolvedBy": resolved_by,
                    "needs": needs,
                    "touchedBy": [],
                }
                if ref.io is not None and ref.kind not in NO_IO_KINDS:
                    row["io"] = ref.io
                    row["ioMeaning"] = _PERMITTED
                here = defined_here.get(key)
                if here is not None:
                    row["definedIn"] = {"source": here["sourceName"], "line": here["line"],
                                        "group": here["group"], "era": here["source"]}
            row["touchedBy"].append(_touch(res, ref))

    artifacts = sorted(rows.values(),
                       key=lambda r: (_CLASS_ORDER.get(r["kind"], 9), r["artifact"]))
    for row in artifacts:
        row["touchedBy"].sort(key=lambda t: (t["resource"], t["field"]))
    excluded_rows = sorted(excluded.values(), key=lambda r: (r["kind"], r["name"]))
    for row in excluded_rows:
        row["touchedBy"].sort(key=lambda t: (t["resource"], t["field"]))

    return {
        "format": FORMAT_ARTIFACTS,
        # The subject key. mainframe_artifacts.fetch reads program/job/region to know what
        # NOT to fetch; without this the region asks the estate for itself.
        "region": region.applid or (region.sources[0] if region.sources else "?"),
        "sources": list(region.sources),
        "note": _ARTIFACTS_NOTE,
        "sit": dict(sorted(region.sit.items())) or None,
        "grplist": list(region.grplist),
        "provides": provides(region),
        "artifacts": artifacts,
        "excluded": excluded_rows,
        "flags": list(region.flags) + _conflicts(region),
    }


# --------------------------------------------------------------------------- #
# lineage - the wiring, and the reverse index
# --------------------------------------------------------------------------- #

_LINEAGE_NOTE = (
    "How work starts in this region and what runs when it does. `entryPoints` is every "
    "definition that STARTS a transaction - a terminal, a URIMAP, a TCPIPSERVICE, a queue "
    "write that trips a TRIGGERLEVEL, an MQ message, the SIT's GMTRAN. `transactions` "
    "carries the reverse index: for each transaction, the program it runs and every entry "
    "point that starts it. `unreachable` is the transactions nothing in these definitions "
    "starts - which is normal and is NOT evidence they are dead: see `boundary`.")

#: What this view cannot see. Stated in the output rather than left for the reader to
#: infer, because every one of these gaps makes a transaction look less connected than it
#: is, and a modernization decision gets made on exactly that impression.
_BOUNDARY = [
    "a user typing a four-character transaction id at a terminal starts it, and no "
    "definition anywhere records that. It is the commonest entry point in most regions.",
    "EXEC CICS START, and pseudo-conversational EXEC CICS RETURN TRANSID, start a "
    "transaction from inside a program. That is in the program source, which this package "
    "does not read - the COBOL and assembler tools emit those as cics-transaction rows, "
    "and bind_program_artifacts is where the two halves meet.",
    "which files, queues and maps a transaction actually uses is in its program, not in "
    "its definition. A FILE definition says what the region PERMITS.",
    "PLTPI and PLTSD programs, and the transactions in the XLT, are named by SIT suffixes "
    "rather than by the SIT itself; those members are not parsed yet.",
    "a transaction routed to another region by REMOTESYSTEM runs a program this region "
    "does not define, and that boundary is not crossed here.",
]


#: The program the CICS region runs. Its DD statements are the region's.
REGION_PROGRAM = "DFHSIP"

#: CICS's own DDs on that step - the CSD, the temporary-storage and transient-data
#: datasets, the trace and log datasets, the load libraries. None of them is an application
#: file, and matching one to a FILE definition would be wrong; they are reported as the
#: region's own datasets so a reader can see what the region is built on.
_SYSTEM_DD = {
    "STEPLIB": "the CICS authorised load library",
    "DFHRPL": "the application load-module search path - the LIBRARY definitions rank "
              "ahead of it, and a program row resolves through both",
    "DFHCSD": "the CSD itself: the VSAM file these definitions live in",
    "DFHTEMP": "auxiliary temporary storage", "DFHINTRA": "intrapartition transient data",
    "DFHAUXT": "auxiliary trace A", "DFHBUXT": "auxiliary trace B",
    "DFHLCD": "the local catalog", "DFHGCD": "the global catalog",
    "DFHDMPA": "dump dataset A", "DFHDMPB": "dump dataset B",
    "SYSIN": "the SIT override deck", "SYSPRINT": "spool", "MSGUSR": "spool",
    "DFHCXRF": "spool",
}


def bind_jcl_region(region: Region, jcl_lineage: dict, *,
                    step: Optional[str] = None) -> Region:
    """Bind this region's file names to datasets from its startup job's DD statements.

    Takes a plain **dict** - a ``jcl-dependencies`` lineage view - and mutates and returns
    the Region, so both views see the datasets afterwards. This package imports nothing
    from the JCL side.

    On a CSD-era estate this is corroboration: the DD and the ``DEFINE FILE`` DSNAME should
    agree, and a disagreement is a real finding. **On a macro-era estate it is the only
    route**, because a ``DFHFCT`` entry carries no DSNAME at all - so a file parsed from a
    macro deck has a name and nothing behind it until this runs.

    Three outcomes per DD, all reported: it is one of CICS's own (the CSD, the trace
    datasets, DFHRPL); it matches a FILE definition or a TDQUEUE's DDNAME; or it matches
    nothing, which is a finding rather than an error - a DD with no definition is either a
    macro-era file whose deck was not supplied, or dead JCL.
    """
    bindings = [b for b in jcl_lineage.get("ddBindings") or []
                if (step is None and b.get("program") == REGION_PROGRAM)
                or (step is not None and b.get("step") == step)]
    if not bindings:
        region.flags.append(
            "the JCL lineage view has no DD statements for a %s step, so no file was "
            "bound from it. The region's datasets are on the step that runs %s"
            % (REGION_PROGRAM, REGION_PROGRAM))
        return region

    files = {res.name: res for res in region.by_kind("FILE")}
    by_ddname: Dict[str, Resource] = {}
    for res in region.resources:
        for ref in res.references:
            if ref.field == "DDNAME" and ref.name:
                by_ddname[ref.name] = res

    system: List[dict] = []
    bound: List[dict] = []
    unmatched: List[dict] = []

    for binding in bindings:
        ddname, dataset = binding.get("ddname"), binding.get("dataset")
        if not ddname:
            continue
        if ddname in _SYSTEM_DD:
            system.append({"ddname": ddname, "dataset": dataset,
                           "role": _SYSTEM_DD[ddname]})
            continue

        res = files.get(ddname) or by_ddname.get(ddname)
        if res is None:
            unmatched.append({
                "ddname": ddname, "dataset": dataset,
                "reason": "no FILE definition of this name, and no TDQUEUE naming it as a "
                          "DDNAME. Either the group that defines it was not supplied, or "
                          "the region defines it in a macro-era FCT, or the DD is dead"})
            continue

        # A `file`-kind DDNAME row is a name awaiting a dataset, so it never counts as an
        # existing binding - only a real DSNAME does.
        existing = next((r for r in res.references if r.kind == "dataset"), None)
        if existing is None:
            res.references.append(Reference(
                field="DDNAME", name=dataset or "", kind="dataset", relation="binds",
                evidence=EVIDENCE_LITERAL,
                io=permitted_io(res.attributes) if res.kind == "FILE" else None,
                note="bound from the %s DD on the region startup job - the definition "
                     "itself carries no DSNAME, which is normal for a macro-era FCT"
                     % ddname))
            bound.append({"ddname": ddname, "dataset": dataset, "resource": res.name,
                          "resourceType": res.kind, "via": "the region startup JCL"})
        elif dataset and existing.name != dataset:
            res.flags.append(
                "the region startup job binds %s to %s, but this definition says %s. "
                "Both are reported and neither is preferred - which one the region runs "
                "with depends on which of these sources is current"
                % (ddname, dataset, existing.name))
            bound.append({"ddname": ddname, "dataset": dataset, "resource": res.name,
                          "resourceType": res.kind, "via": "the region startup JCL",
                          "disagreesWith": existing.name})
        else:
            bound.append({"ddname": ddname, "dataset": dataset, "resource": res.name,
                          "resourceType": res.kind, "via": "corroborated - the DD and the "
                                                           "definition agree"})

    region.jcl = {"source": jcl_lineage.get("source") or jcl_lineage.get("job"),
                  "job": jcl_lineage.get("job"),
                  "systemDatasets": system, "bound": bound, "unmatched": unmatched}
    if unmatched:
        region.flags.append(
            "%d DD statement(s) on the %s step match no definition in these sources: %s"
            % (len(unmatched), REGION_PROGRAM,
               ", ".join(u["ddname"] for u in unmatched)))
    return region


def _definition_index(region: Region) -> Dict[Tuple[str, str], Resource]:
    """(manifest kind, name) -> the Resource that defines it. First definition wins.

    First rather than last, and deliberately not "merged": when a resource is defined
    twice the manifest already carries a conflict flag, and a binder that silently picked
    one would undo exactly the honesty that flag exists to provide. The bound row says
    which definition it used and the flag says there was more than one.
    """
    index: Dict[Tuple[str, str], Resource] = {}
    for res in region.resources:
        index.setdefault((PROVIDES_KIND.get(res.kind, res.kind), res.name), res)
    return index


def _ts_models(region: Region) -> List[Tuple[str, Resource]]:
    """(prefix, resource) for every TSMODEL, longest prefix first.

    Longest first because prefixes nest: CUSTLOG and CUST are both models, and a queue
    called CUSTLOG01 belongs to the more specific one.
    """
    models = []
    for res in region.by_kind("TSMODEL"):
        prefix = res.attributes.get("PREFIX") or res.name
        models.append((prefix, res))
    models.sort(key=lambda pair: (-len(pair[0]), pair[0]))
    return models


def _definition_of(res: Resource) -> dict:
    return {"resourceType": res.kind, "group": res.group, "installed": res.installed,
            "source": res.source_name, "line": res.line, "era": res.source}


def bind_program_artifacts(manifest: dict, region: Region) -> dict:
    """Close a COBOL or assembler manifest's unresolved CICS rows against these
    definitions. Takes a plain dict and returns a NEW one - this package imports no peer.

    Their rows already say what they want. An assembler manifest's ``file`` row carries
    ``needs: "the CICS FILE definition that binds this name to a VSAM dataset - unlike a
    batch ddname, a CICS file is named in the CSD rather than in JCL"``. This supplies it,
    and the FILE case is the payoff: it is the last edge before an online read and a batch
    write meet at the same dataset node.

    **Observed access and permitted access are both kept.** The program's own ``io`` says
    what the module does; ``permittedIo`` says what the region allows. Overwriting the
    first with the second makes every read-only module look like an updater; dropping the
    second loses "permitted update, never updated", which is a finding.
    """
    out = dict(manifest)
    out["artifacts"] = [dict(row) for row in manifest.get("artifacts", []) or []]

    index = _definition_index(region)
    models = _ts_models(region)
    bound = 0
    unbound: List[dict] = []

    for row in out["artifacts"]:
        kind, name = row.get("kind"), row.get("artifact")
        if kind not in _BINDABLE or not name:
            continue

        res = index.get((kind, name))
        via = "definition"
        if res is None and kind == "queue":
            for prefix, model in models:
                if name.startswith(prefix):
                    res, via = model, "prefix"
                    break

        if res is None:
            unbound.append({"artifact": name, "kind": kind,
                            "reason": _UNBOUND_REASON.get(kind, _UNBOUND_DEFAULT)})
            continue

        bound += 1
        row["definition"] = _definition_of(res)
        row["boundVia"] = via
        if via == "prefix":
            row["definition"]["prefix"] = res.attributes.get("PREFIX") or res.name
            row["definition"]["note"] = (
                "matched by TSMODEL PREFIX, not by name - the model governs every queue "
                "whose name starts with it")

        if kind == "file":
            dataset = next((r.name for r in res.references if r.kind == "dataset"), None)
            if dataset:
                row["dataset"] = dataset
            else:
                row["definition"]["note"] = (
                    "this FILE definition carries no DSNAME - on a macro-era FCT the "
                    "dataset is a DD on the CICS region startup JCL, which bind_jcl_region "
                    "supplies")
            permitted = next((r.io for r in res.references
                              if r.kind == "dataset" and r.io), None)
            if permitted:
                row["permittedIo"] = permitted
                row["ioMeaning"] = (
                    "`io` is what this program does; `permittedIo` is what the region "
                    "allows. They are different questions and are not merged")
        elif kind == "cics-transaction":
            runs = next((r.name for r in res.references if r.relation == "runs"), None)
            row["runs"] = runs

    out["cicsBinding"] = {
        "apiVersion": PROGRAM_BINDING_API_VERSION,
        "sources": list(region.sources),
        "region": region.applid,
        "bound": bound,
        "unbound": sorted(unbound, key=lambda u: (u["kind"], u["artifact"])),
    }
    flags = list(out.get("flags") or [])
    if unbound:
        flags.append(
            "%d CICS row(s) found no definition in %s: %s. Each says why - an undefined "
            "name is a real gap, and a BMS map is not one at all"
            % (len(unbound), ", ".join(region.sources) or "these sources",
               ", ".join("%s %s" % (u["kind"], u["artifact"]) for u in unbound)))
    out["flags"] = flags
    return out


def build_cics_lineage(region: Region) -> dict:
    """The wiring: what starts work, what it runs, and what nothing starts."""
    entry_points: List[dict] = []
    started_by: Dict[str, List[dict]] = {}

    def record(name: str, entry: dict) -> None:
        entry_points.append(entry)
        started_by.setdefault(name, []).append(
            {k: entry[k] for k in ("via", "kind", "name", "line")})

    for res in region.resources:
        for ref in res.references:
            if ref.relation not in _STARTS or ref.kind != "cics-transaction":
                continue
            record(ref.name, {
                "transaction": ref.name,
                "via": ref.relation,
                "kind": res.kind,
                "name": res.name,
                "field": ref.field,
                "installed": res.installed,
                "source": res.source_name,
                "line": ref.line,
                "note": ref.note or None,
            })

    gmtran = region.sit.get("GMTRAN")
    if gmtran and gmtran.upper() not in ("NO", "NONE"):
        record(gmtran, {"transaction": gmtran, "via": "starts", "kind": "SIT",
                        "name": "GMTRAN", "field": "GMTRAN",
                        # The SIT is what installs everything else, so an entry point it
                        # states is live by definition - unlike a CSD definition, which is
                        # live only if GRPLIST reaches its group.
                        "installed": INSTALLED_YES,
                        "source": "the SIT", "line": None,
                        "note": "the good-morning transaction, started at logon"})

    transactions: List[dict] = []
    for res in region.by_kind("TRANSACTION"):
        runs = next((r.name for r in res.references if r.relation == "runs"), None)
        transactions.append({
            "transaction": res.name,
            "runs": runs,
            "group": res.group,
            "installed": res.installed,
            "source": res.source_name,
            "line": res.line,
            "startedBy": sorted(started_by.get(res.name, []),
                                key=lambda e: (e["kind"], e["name"])),
            "routedTo": next((r.name for r in res.references
                              if r.relation == "routed-to"), None),
        })
    transactions.sort(key=lambda t: (t["transaction"], t["source"], t["line"] or 0))

    unreachable = [t["transaction"] for t in transactions if not t["startedBy"]]
    entry_points.sort(key=lambda e: (e["transaction"], e["kind"], e["name"]))

    flags = list(region.flags)
    if unreachable:
        flags.append(
            "%d of %d transactions are started by nothing in these definitions. That is "
            "the NORMAL case and is not evidence they are dead - see `boundary`: a user "
            "typing the id, and EXEC CICS START/RETURN TRANSID inside a program, are both "
            "invisible here" % (len(unreachable), len(transactions)))

    return {
        "format": FORMAT_LINEAGE,
        "region": region.applid or (region.sources[0] if region.sources else "?"),
        "sources": list(region.sources),
        "note": _LINEAGE_NOTE,
        "entryPoints": entry_points,
        "transactions": transactions,
        "unreachable": unreachable,
        "boundary": _BOUNDARY,
        "flags": flags,
    }
