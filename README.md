# cics-dependencies

Parse IBM CICS **resource definitions** — the CSD, the table macro decks, the SIT, BAS
and bundles — and recover what a region actually wires together: which program a
transaction runs, which VSAM dataset is behind a CICS file name, which queue write starts
a task, and which of it is defined but never installed.

The COBOL says what a program does. The JCL says which dataset a batch ddname is. The
assembler says what a module calls. None of them can say what `FILE('CUSTFILE')` *is* —
unlike a batch ddname, a CICS file is named in the **CSD**, not in JCL, and that binding
is the last edge missing before an online read and a batch write meet at the same dataset
node.

This is the definition side of the family. Its peers already emit the unresolved half:
an `asm-dependencies` or COBOL manifest carries `cics-transaction`, `terminal-map`,
`file` and `queue` rows whose `needs` field says, in so many words, *the CSD entry that
says which program this transaction runs*. This package supplies it.

## Install

```bash
pip install cics-dependencies
```

It depends on `mainframe-artifacts` (the estate boundary and the two-stage dependency
retrieval, shared with the COBOL, JCL, Easytrieve and assembler tools) and on nothing
else. Pure Python standard library, Python >= 3.9.

`mainframe-artifacts` ships from the
[mainframe-common](https://github.com/paulhowarda-bit/mainframe-common) repository (one
repo, several distributions; its `mainframe-artifacts/` subdirectory). Until it is on an
index, install it straight from that repo:

```bash
pip install "mainframe-artifacts @ git+https://github.com/paulhowarda-bit/mainframe-common#subdirectory=mainframe-artifacts"
```

**It depends on none of `cobol-xstate`, `jcl-dependencies`, `eztrieve-dependencies` or
`asm-dependencies`.** The five are peers that meet at plain manifest dicts.
`tests/test_boundaries.py` enforces that none of them is importable from here.

## Use

```bash
cics-dependencies APP.CSD                          # 2 views + both retrieval reports -> ./out
cics-dependencies APP.CSD --sit DFHSIT.asm         # ...and decide what is installed
cics-dependencies APP.CSD OLD.CSD                  # one region from several decks
cics-dependencies APP.CSD --target lineage         # just the wiring
cics-dependencies APP.CSD --summary                # + a scoreboard on stderr

# Close the joins no single tool can make
cics-dependencies APP.CSD --bind-jcl out/cicsapp1.jcl.lineage.json
cics-dependencies APP.CSD --bind-program out/custinq.asm.artifacts.json

# Gather where the estate is reachable, model where it is not
cics-dependencies APP.CSD --gather-only ./bundle
cics-dependencies APP.CSD --from-bundle ./bundle   # no network at all
```

As a library:

```python
from cics_dependencies.api import analyze

a = analyze([("APP.CSD", open("APP.CSD").read())], retrieve=False)
a.artifacts()          # what these sources define, and everything they name
a.lineage()            # what starts work here, what it runs, what nothing starts
a.bind(manifest)       # close a COBOL/assembler manifest's CICS rows
a.bind_jcl(lineage)    # the region startup job's DD statements
```

## Status

**Complete, and honest about which half is proven.** All five definition syntaxes parse —
CSD decks and `DFHCSDUP` extracts (bare or instream in a JCL job), macro table decks,
the SIT, CICSPlex SM BAS, and CICS bundles — plus BMS field lineage, the install closure,
stage-1 retrieval, both views, both binders and the command line.

**Four of the six paths are validated against real public source** — the CSD path (AWS
CardDemo, IBM example-health-apis), the macro-table path, the SIT and BMS (DOGECICS, which
runs on KICKS and ships real `KIKPCT`/`KIKPPT`/`KIKFCT` decks, a real SIT and a 60KB
mapset). **BAS and bundles are written from the manuals only** — no public source carries
either beside the definitions it belongs to — so treat those two as unproven until your own
decks have been through them.

`python tools/fetch_corpus.py` downloads the corpus; it is never vendored, partly because
one member has no licence file at all.

Under the covers:

```python
from cics_dependencies.csd import parse_csd
from cics_dependencies.sit import parse_sit
from cics_dependencies.install import apply_install_state
from cics_dependencies.views import build_cics_artifacts

region = parse_csd(open("CARDDEMO.CSD").read(), source_name="CARDDEMO.CSD")
parse_sit(open("DFHSIT.asm").read(), region=region)   # optional; decides `installed`
apply_install_state(region)
build_cics_artifacts(region)
```

Over AWS CardDemo that gives **64 `provides` rows and 31 artifacts** — 18 programs the
transactions run, 10 datasets (8 VSAM files, a load library, the internal reader), 3
transactions — with 3 excluded and no flags.

`build_cics_lineage(region)` is the other view: every entry point that starts work
(terminal, URIMAP, TCPIPSERVICE, a queue write that trips a TRIGGERLEVEL, MQ, the SIT's
GMTRAN), each transaction with the program it runs and a `startedBy` reverse index, and
the transactions nothing in the definitions starts — stated as normal rather than as dead
code, because the commonest entry point in any region is a user typing four characters and
no definition records that.

And `bind_program_artifacts(manifest, region)` closes a peer's unresolved CICS rows.
Against a real `asm-dependencies` manifest for a module that reads `FILE('CUSTMAST')`:

```
file  CUSTMAST  io=read  permittedIo=read-write  dataset=PROD.CUSTOMER.MASTER
```

That row is the point of the whole package — the assembler manifest could not say what
`CUSTMAST` is, and now an online read and a batch write meet at the same dataset node. It
also shows the second rule: `io` is what the module does, `permittedIo` is what the region
allows, and they are never merged.

`bind_jcl_region(region, jcl_lineage)` reads the other half — a `jcl-dependencies` lineage
view of the CICS startup job. On a CSD-era estate that is corroboration; on a macro-era one
it is the only route, since a `DFHFCT` entry carries no DSNAME at all. It sorts every DD on
the `DFHSIP` step into three: CICS's own (the CSD, DFHRPL, the trace and TS/TD datasets), a
file or queue definition it binds, or a DD that matches nothing — reported as a finding,
because that is either a macro-era file whose deck was not supplied or dead JCL.

All four outputs are byte-locked by `tools/byteproof.py`, which the suite runs under two
`PYTHONHASHSEED` values.

Stage 1 closes over what the region names and does not hold: a LIST named by `GRPLIST`, a
GROUP a LIST adds, the `DFHPLTPI`/`DFHXLT` members a SIT suffix names. It replays the
MODEL's gaps rather than a parser's resolver, because a CSD deck includes nothing
textually. IBM's own `DFHLIST` is never asked for.

The three eras produce **one manifest shape**: a BAS `TRANDEF`'s `PROGRAM`, a
`DFHPCT TYPE=ENTRY,PROGRAM=` and a `DEFINE TRANSACTION ... PROGRAM()` all come out as the
same row, because all three read the same table in `resources.py`. What differs is what
they cannot say — a macro table has no GROUP, so the install closure cannot decide it; a
BAS resource is installed by a RESDESC; and an FCT entry has no dataset until the region
JCL supplies one. Each says so on the row.

BMS is the one field level CICS has: `DFHMSD TYPE=DSECT` turns a field `CUSTNO` into
`CUSTNOL`, `CUSTNOF`, `CUSTNOA`, `CUSTNOI` and `CUSTNOO`, which is mechanical and joins
straight to COBOL data names. Everything else CICS names — COMMAREAs, containers, TS
records — is named without a layout, and the view says so rather than implying one.

`CLAUDE.md` has the invariants and what is still owed.

## The two directions

A dependency question about CICS is really two questions, and the manifest answers them
separately.

**What a definition depends on** — its attribute fields. In a declarative resource
definition the keyword *is* the evidence, so `DEFINE TRANSACTION(MENU) PROGRAM(MENU001)`
yields a `program` row with `evidence: literal` and `field: PROGRAM`. Every such field is
enumerated in `resources.py`, one table, so a reader can see the whole edge set at once
rather than inferring it from the parser.

**What depends on a definition** — the `provides` index, plus binders. This package does
not go scanning the estate for referrers. It publishes what it defines and offers the
join, the way `asm-dependencies` publishes its entry points:

```python
bind_program_artifacts(manifest, region)   # a COBOL/asm manifest's CICS rows -> definitions
bind_jcl_region(region, jcl_lineage)       # the DFHSIP job's DDs -> DFHRPL, FCT-era files
```

Both take plain dicts and return plain dicts.

## Three eras, one model

| era | artifact parsed | defines a transaction as |
|---|---|---|
| macro tables | `DFHPCT` / `DFHPPT` / `DFHFCT` / `DFHDCT` / `DSNCRCT` assembler decks | `DFHPCT TYPE=ENTRY,TRANSID=MENU,PROGRAM=MENU001` |
| CSD | `DFHCSDUP` input decks and `EXTRACT` / `LIST` output | `DEFINE TRANSACTION(MENU) GROUP(APPG) PROGRAM(MENU001)` |
| BAS / bundles | CICSPlex SM `BATCHREP` decks; a bundle's `META-INF/cics.xml` | `CREATE TRANDEF NAME(MENU) PROGRAM(MENU001)` |

The CSD itself is a VSAM KSDS. It is not parsed and never will be — the parseable
artifact is always the `DFHCSDUP` deck or its `EXTRACT` output, which is what sites keep
in source control.

**The eras differ in one way that changes the output.** An FCT entry usually carries no
`DSNAME`: the file-to-dataset binding is a **DD in the CICS region startup JCL**. So on a
macro-era estate that edge is recoverable only by joining a `jcl-dependencies` lineage
view of the `DFHSIP` job. Without one the row says the dataset is unbound; it is never
omitted, because an omitted row reads as a file with no dataset behind it.

## A DEFINE is not an installed transaction

Every row carries an `installed` state alongside its evidence, because they answer
different questions — the same split `asm-dependencies` keeps between `evidence` and
`conditional`.

| `installed` | meaning |
|---|---|
| `installed` | the resource's GROUP is in a LIST named by the SIT's `GRPLIST` |
| `defined-not-installed` | the DEFINE exists in the CSD and nothing installs it |
| `unknown` | no SIT in hand — the honest default, not a failure |

Treating every DEFINE as live inflates a dead estate by however many groups it has
accumulated; treating unknowns as dead hides live ones. Runtime `CEDA`/`CEMT` installs
and `EXEC CICS CREATE` are invisible to any static parse and are flagged as such.

## What it will not claim

* **A `FILE` definition's `READ`/`UPDATE`/`ADD`/`DELETE`/`BROWSE` is permitted access,
  not observed access.** The program manifest says what actually happens. Reporting the
  capability as the usage would make every read-only file look updated.
* **A `TSMODEL` matches by `PREFIX`.** Joining a program's `WRITEQ TS QUEUE('CUSTWRK1')`
  to a model is a prefix match, and it is reported as one.
* **A COMMAREA layout is a convention, not a definition.** `LINK PROGRAM(X)
  COMMAREA(Y) LENGTH(n)` names a caller-side structure; the callee's `DFHCOMMAREA` is
  matched by nothing the source states. Both copybook names go in `candidates`.
* **`REMOTESYSTEM` means the resource is in another region.** That is a real edge and a
  real boundary; it is never resolved locally.
* **RACF `TCICSTRN`/`GCICSTRN` profiles say who may run a transaction.** They live in the
  security database, not in any source artifact, and their absence is flagged rather than
  left to read as "unsecured".
* **IBM-supplied groups** (`DFH$*`, `DFHLIST`, `CEMT`/`CESN`/`CEDA`) classify as
  `ibm-runtime` and are excluded from the manifest, so they are not chased through the
  estate.

## The one field level that is real

BMS is the only CICS artifact that yields byte-addressable field lineage. `DFHMSD` /
`DFHMDI` / `DFHMDF` give the field name, `POS`, `LENGTH`, `ATTRB`, `PICIN`/`PICOUT` and
`OCCURS`, and the `TYPE=DSECT` symbolic map is mechanically derivable — `FIELD` yields
`FIELDL`, `FIELDF`, `FIELDA`, `FIELDI`, `FIELDO` — so a screen field joins to the exact
COBOL data names a program moves to and from.

Everything else at the field level (COMMAREA, containers, TS/TD records) is named but not
laid out, and the manifest says so rather than implying a mapping.

## Development

```bash
# mainframe-artifacts comes from a sibling mainframe-common checkout (or the git+ line above)
python -m pip install -e ../mainframe-common/mainframe-artifacts -e .
python -m pytest -q
```

From a bare dual-checkout — mainframe-common beside this repo, nothing installed — the
suite finds `../mainframe-common/mainframe-artifacts` automatically (override with
`MAINFRAME_COMMON_REPO`); without either, the run ends as one clean skip naming the exact
pip command.

Output will be byte-stable and deterministic once there is output: `tools/byteproof.py`
joins the repo with the first view.
