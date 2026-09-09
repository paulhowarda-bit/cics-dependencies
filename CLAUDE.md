# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this
repository.

## What this is

Parses IBM CICS resource definitions — CSD decks and `DFHCSDUP EXTRACT` output, the table
macro decks (`DFHPCT`/`DFHPPT`/`DFHFCT`/`DFHDCT`/`DSNCRCT`), the SIT, CICSPlex SM BAS
`BATCHREP` decks and bundle manifests — and extracts the resource graph: which program a
transaction runs, which dataset a CICS file name binds, which queue write triggers a task,
and whether any of it is actually installed. See README.md for the user-facing
description.

**Complete.** Every module in the architecture below is implemented: all five definition
syntaxes (CSD, macro tables, SIT, BAS, bundles) plus BMS, the install closure, stage-1
retrieval, both views, both binders, and the command line. Output is byte-locked by
`tools/byteproof.py`.

**Validated against real source: the CSD path, the macro-table path, the SIT and BMS.**
AWS CardDemo, IBM's example-health-apis and DOGECICS/KICKS between them cover four of the
six. **BAS and bundles are manual-only** - no public source carries either beside the
definitions it belongs to - and so is a paginated `DFHCSDUP EXTRACT` report. Say so wherever
it matters: a row from a BAS deck and a row from `CARDDEMO.CSD` do not carry the same
weight.

## Setup

The one dependency, `mainframe-artifacts`, ships from the **mainframe-common** repository
and is normally a sibling checkout rather than an install:

```
code/
  mainframe-common/mainframe-artifacts/    <- the dependency
  jcl-dependencies/                        <- peer (region JCL, the DFHSIP job)
  asm-dependencies/                        <- peer (EXEC CICS in assembler)
  cobol-xstate-json/                       <- peer (EXEC CICS in COBOL)
  eztrieve-dependencies/                   <- peer
  cics-dependencies/                       <- here
```

`tests/_mainframe_common.py` puts the sibling's `src` on `sys.path` when the distribution
is not installed; override with `MAINFRAME_COMMON_REPO`. When neither is found,
`tests/conftest.py` ignores every module except `test_sibling_distribution.py`, so the run
ends as one clean skip naming the pip command.

No install is needed to run the suite — `pyproject.toml` sets `pythonpath = ["src",
"tests"]`.

## Commands

```bash
python -m pytest -q                                      # the suite
python -m pytest tests/test_csd.py -q                    # one file
python -m pytest -q -k "remark or usage_map"             # by name
python -m pytest -q tests/test_corpus.py                 # the real-source tests only
python -m pyflakes src/cics_dependencies/*.py tests/*.py tests/fakes/*.py tools/*.py

python tools/fetch_corpus.py                             # the public validation corpus
python tools/fetch_corpus.py --check                     # what is present, fetch nothing
python tools/byteproof.py --check goldens/views.sha256   # byte-stability ratchet
python tools/byteproof.py --record goldens/views.sha256  # re-record (deliberately only)
python tools/refresh_fixture.py --check                  # the cross-repo binder contracts
python tools/refresh_fixture.py --record                 # re-run the peers, rewrite them
python tools/make_examples.py --check                    # the generated column examples
python tools/make_examples.py                            # regenerate them
```

The ratchet is also RUN BY THE SUITE, under two `PYTHONHASHSEED` values
(`tests/test_byteproof.py`). The sibling repositories leave the two-seed run to the
operator; here it is a test, because a set comprehension emitted without sorting is stable
on one seed and different on the next, and a single-seed record captures whichever it saw.

`pyproject.toml`'s `pythonpath` applies to **pytest only**, so a bare
`python -m cics_dependencies` fails with `No module named` unless the package is installed
or the path is given explicitly — note `;` is the separator on Windows, `:` elsewhere:

```bash
python -m pip install -e ../mainframe-common/mainframe-artifacts -e .
export PYTHONPATH="src;tests;../mainframe-common/mainframe-artifacts/src"
```

Then (`--no-fetch` because the real estate client is not installed here):

```bash
python -m cics_dependencies examples/appregn.csd --outdir ./out --no-fetch --summary
python -m cics_dependencies examples/appregn.csd --sit examples/appregn.sit \
    --outdir ./out --no-fetch
python -m cics_dependencies examples/appregn.csd examples/legacy.csd \
    --outdir ./out --no-fetch            # one region, two decks, a flagged conflict
python -m cics_dependencies examples/appregn.csd --outdir ./out --no-fetch \
    --bind-jcl tests/fixtures/cicsapp1.jcl.lineage.json
python -m cics_dependencies examples/custinq.csd --outdir ./out --no-fetch \
    --bind-program tests/fixtures/custinq.asm.artifacts.json
python -m cics_dependencies examples/appregn.csd --sit examples/appregn.sit \
    --outdir ./out --jobs 1 --fetcher fakes.estate:fetch_artifact   # needs tests/ on path
```

`tests/fakes/estate.py` is the deterministic stand-in for the estate service. Its table is
shaped so the closure has to run TWICE: `RPTLIST` is fetched because GRPLIST names it, and
`REPORTG` because `RPTLIST` adds it - which is only knowable once `RPTLIST` has been read.

## Architecture

One pipeline, each stage ignorant of the next. Mirrors `asm-dependencies` deliberately:

```
lexer.py        physical text -> statements. TWO dialects, one module, because a deck's
                dialect is not reliably declared:
                  * CSD command syntax (DFHCSDUP): free-form to column 72, `*` comments,
                    and a statement that runs until the next COMMAND VERB - not until a
                    trailing comma, and emphatically not by indentation. `lex_csd` takes
                    the verb set, which is how BAS reuses it.
                  * assembler (macro table decks and BMS): columns 1-71, col-72
                    continuation resuming at col 16, an operand field ending at the first
                    blank outside quotes and parens.
                NOT handled: a paginated DFHCSDUP EXTRACT / LIST REPORT, which is a
                report rather than a deck. See "What is left".
detect.py       which of the five kinds a source is, and where inside it the deck starts:
                a CSD deck and a macro deck both arrive instream in a JCL job as often as
                bare. BMS and macro decks are told apart by which macros they invoke,
                never by suffix - both are assembler with a label in column 1.
csd.py          DEFINE / ADD / COPY / APPEND / REMOVE / LIST -> Resource objects
tables.py       DFHPCT / DFHPPT / DFHFCT / DFHDCT / DFHTCT / DFHTST / DFHPLT / DFHXLT /
                DSNCRCT -> the SAME Resource objects
sit.py          DFHSIT source + SIT overrides + the DFHSIP step's PARM -> Region
bas.py          CICSPlex SM BATCHREP (EYU9XDBT) CREATE ... -> Resource objects
bundles.py      META-INF/cics.xml <define> + bundle parts -> Resource objects
bms.py          DFHMSD / DFHMDI / DFHMDF -> mapsets, maps, fields, symbolic-map names
resources.py    THE TABLE: for every resource kind, which attribute fields name which
                artifact kinds, in which direction. Pure data, no parsing.
model.py        Resource / Reference / Group / ListDef / Region dataclasses
install.py      GRPLIST -> LIST -> GROUP closure; the `installed` state of every resource
classify.py     IBM-supplied groups and transactions -> ibm-runtime, not chased
prefetch.py     replay-until-quiet closure over LISTs, GROUPs and SIT-named table
                members not in hand. What is replayed is the MODEL's gaps, not a
                parser's resolver: a CSD deck includes nothing textually, so there is
                no resolver to record
views.py        Region -> the two JSON views + the two cross-repo binders
```

`api.py` wires prefetch -> parse -> views -> fetch; `cli.py` is a thin front end over it.
Nothing below `views.py` knows about JSON, and nothing above the parsers decides evidence.

### Invariants that span files

**Five peer packages, no imports between them.** They share only `mainframe_artifacts` and
meet at plain dicts. `tests/test_boundaries.py` runs child interpreters with those packages
blocked *and* greps every module's import lines — and the module inventory test fails if a
new module is added without being listed, because an unlisted module is silently unchecked.

**`resources.py` is the single source of truth for the edge set.** Every attribute that
names another artifact is in that table, and the parsers read it rather than restating it.
A `DEFINE` attribute handled in `csd.py` but absent from the table produces a silently
missing edge with no flag — which is the failure mode this whole family exists to avoid.
The same table serves `tables.py`, so a `DFHPCT TYPE=ENTRY,PROGRAM=` and a
`DEFINE TRANSACTION ... PROGRAM()` produce an identical row from different source eras.

**Two eras coexist, and a conflict between them is never resolved.** The estate has CSD
decks AND surviving `DFHPCT`/`DFHFCT`/`DFHDCT` decks, some of which are no longer live.
When both define the same resource and disagree - `DFHPCT` says `MENU` runs `MENU001`, the
CSD says `MENU009` - BOTH rows are emitted, each tagged with its `Resource.source`, and a
flag names the conflict. Neither wins. A stale deck in a PDS is textually identical to a
live one, so picking a winner is a guess presented as a fact, and it is a guess a
modernization decision then gets made on. The SIT settles it where there is one
(`PCT=`/`FCT=` suffixes against `GRPLIST=`), which is another reason `--sit` matters.

**Four lexer rules that real decks taught and synthetic fixtures would not have.** Each
one fails silently rather than raising, which is why they are invariants and not comments:
a value may contain blanks and commas (`DEFINETIME(22/06/10 20:03:53)`, `WAITTIME(0,0,0)`)
so values are read by paren balance, never split on whitespace; `DESCRIPTION(...)` sits in
the same column as `DEFINE`, so indentation is not the continuation signal; `ADD`, `DELETE`
and `LIST` are DFHCSDUP commands AND ordinary FILE attributes, disambiguated by whether the
verb is immediately followed by `(`; and a deck arrives at least as often instream in a JCL
job as it does bare, so `detect.py` strips the wrapper - replacing it with blank lines, so
every line number still points at the file the reader has open.

**Evidence and `installed` answer different questions.** Evidence says how well the name is
known (`literal` for a name in the definition, `dynamic` for a CICS argument that is a data
area, `prefix` for a TSMODEL match); `installed` says whether the resource is live at all.
Folding them loses the case that occurs most: a perfectly known definition in a group
nothing installs.

**`unknown` is the honest default for `installed`, not a failure.** A CSD parsed without a
SIT cannot know what `GRPLIST` names. Defaulting to `installed` inflates a dead estate;
defaulting to `defined-not-installed` hides live resources.

**Capability is not usage.** A `FILE` definition's `SERVREQ=` (macro) or
`READ/UPDATE/ADD/DELETE/BROWSE` (CSD) is what the region *permits*. The `io` on the row is
tagged as permitted access, and the *observed* access comes from a program manifest through
`bind_program_artifacts`. Collapsing the two makes every read-only file look updated.

**A macro-era FCT has no dataset.** The binding is a DD on the `DFHSIP` step, so the row is
emitted unbound with a flag naming the region JCL, never omitted. An omitted row is
indistinguishable from a file with nothing behind it.

**A CICS argument's quoting is its evidence** — the same IBM rule the assembler side
follows. Do not "improve" a `dynamic` row by resolving the data area.

**`cics-transaction` and `terminal-map` carry no `io`.** House rule across the family, same
as `program`, `proc` and `macro`. `file` uses the Easytrieve `read-write` spelling;
`db2-table` uses the JCL side's `read+write`. Two spellings of one idea, kept per KIND so a
consumer's rule is the same wherever a row of that kind came from.

**The subject key is `region`.** `mainframe_artifacts.fetch` reads
`manifest.get("program") or manifest.get("job") or manifest.get("region")` to know what NOT
to fetch. This subject is neither a program nor a job, so without that third arm the region
requests ITSELF from the estate as its own dependency — the same failure the `job` arm was
added to fix for JCL. The upstream change is mainframe-common commit `2e02fb2`; keep
`views.build_cics_artifacts` emitting the key under that name, and
`tests/test_views.py::test_the_subject_key_is_region` is what notices if it is renamed.

**New kinds need registering.** Adding an artifact `kind` requires a matching entry in
`mainframe_artifacts.fetch._KIND_TYPE` (and `artifact_service.EXT_FOR_TYPE`) in
mainframe-common — otherwise stage 2 reports it `skipped: no known retrieval type`, which
is false. `cics-transaction`, `queue`, `terminal-map`, `program`, `file`, `dataset`,
`copybook` and `macro` are already registered; `csd` and `bms` already exist as retrieval
types. The kinds this package adds (`cics-group`, `cics-list`, `cics-profile`,
`cics-tranclass`, `cics-connection`, `cics-urimap`, `cics-tcpipservice`, `cics-library`,
`cics-lsrpool`, `cics-journalmodel`, `cics-jvmserver`, `cics-bundle`, `cics-partitionset`,
`db2-plan`) are **not**.

DECIDED: leave them unregistered for now. They go in `excluded` with the reason — the
pattern `asm-dependencies` uses for `psb` and `segment` — until a real corpus run shows
which of them actually appear in output often enough to be worth fetching. Registering
fourteen kinds up front is a guess at a registry; registering the ones the CardDemo and
health-apis runs produce is a measurement. `tests/test_resources.py` asserts both halves of
this claim, so the day any of them is registered upstream the suite goes red and says to
move it.

## The validation corpus

Examples written for this repository only prove the tool does what it was built to do. The
real check is public CICS material, fetched into a gitignored directory by
`tools/fetch_corpus.py` so nothing third-party is committed here — the same arrangement
`asm-dependencies` used for IFOX and learnasm370, and `tests/test_corpus.py` skips cleanly
when the corpus is absent.

* **[AWS CardDemo](https://github.com/aws-samples/aws-mainframe-modernization-carddemo)**,
  Apache 2.0. `app/csd/CARDDEMO.CSD` is a real DFHCSDUP deck — 505 lines, **64 DEFINEs**:
  18 PROGRAM, 18 TRANSACTION, 17 MAPSET, 8 FILE (KSDS and AIX paths, with `DSNAME`,
  `RLSACCESS`, `LSRPOOLNUM`), 2 LIBRARY, 1 TDQUEUE, all in one group `CARDDEMO`. (Counted
  by running the parser over it. An earlier draft of this file said 69/24/17, taken from a
  summary of the file rather than the file — the sort of thing this repo exists to stop
  doing.) The same repo carries
  the COBOL, the BMS maps, the copybooks and the batch JCL, so **both ends of every binder
  are in one place** — `FILE(ACCTDAT) -> DSNAME` can be checked against the COBOL that
  reads it and the JCL that loads it.
  Its gap: no `ADD GROUP/LIST` and no SIT, so every row comes out `installed: unknown` and
  the install closure is untestable from it alone.
* **[IBM example-health-apis](https://github.com/IBM/example-health-apis)**,
  `HCAZ_Source/IBMUSER.ZMOBILE.JCL/.expanded/@CDEF121.JCL` — a real DFHCSDUP job carrying
  exactly what CardDemo lacks: `Remove Group(HCAZMOBL) List(HCAZLIST)`,
  `Delete Group(...) All`, `Add Group(HCAZMOBL) List(HCAZLIST)`. It is also **mixed case**
  (`Define Transaction(HCAZ)`), which CardDemo alone would have hidden from the lexer.
* **[cicsdev/cics-java-jcics-samples](https://github.com/cicsdev/cics-java-jcics-samples)**
  ships a `DFHCSD.txt` per sub-project;
  **[jt-nti/hello-cics](https://github.com/jt-nti/hello-cics)** has the DFHCSDUP JCL
  wrapper with its `PARM='CSD(READWRITE),PAGESIZE(60),NOCOMPAT'`.

* **[DOGECICS](https://github.com/mainframed/DOGECICS)**, **no licence file** - which is
  itself a reason the corpus is fetched and never vendored. It runs on KICKS, a
  CICS-compatible system whose tables are the same shape as IBM's under different names,
  and it supplies the two things nothing else does:
  * `SIT/KIKPCTDO`, `KIKPPTDO`, `KIKFCTDO` - **real macro table decks**, 85 resources.
  * `SIT/KIKSITDO` - **a real SIT**, the only one in the corpus.
  * `BMS/DOGEMMAP` - a real 60KB BMS mapset: 180 fields, 6 of them named.

**Four defects this deck found, none of which a synthetic fixture would have:**

1. **An HLASM remark is not operand text.** `PROGRAM=KSGMPGM NO REFRESH` - the operand
   field ends at the first blank outside quotes and parens. Read whole, the program became
   `KSGMPGM NO REFRESH`, a name resolving to nothing, in a row that looked ordinary.
   `lexer._operand_field`.
2. **A mapset can be spelt `PROGRAM=KSGMAP,USAGE=MAP`.** Keyed on the operand name alone,
   every map in the region was reported as a program.
3. **A table deck arrives instream in an ASSEMBLE job**, not as a bare member - KICKS ships
   each as a complete `PGM=IFOX00` job. Handed the job whole the lexer found no table macro
   and reported a deck that contributed nothing. `detect.macro_deck_source`.
4. **The macro prefix is not always `DFH`.** KICKS uses `KIK`, and so does any shop that
   wraps IBM's macros. `resources.MACRO_PREFIXES` and `Region.macro_prefix` - which also
   decides what a SIT's suffixes NAME: `FCT=DO` under a `KIKSIT` is the member `KIKFCTDO`,
   and asking the estate for `DFHFCTDO` gets a not-found that is about this package rather
   than about the estate.

A fifth is a limit rather than a defect, and is flagged rather than solved: this handles a
renamed macro whose **operands still match**. A site macro with its own operand vocabulary
would not be caught by it, and `tables.py` says so on every aliased deck.

**Still not found anywhere public:** a paginated `DFHCSDUP EXTRACT` *report* (as opposed to
the DEFINE-shaped extract CardDemo is), a CICSPlex SM `BATCHREP` deck, and a CICS bundle
with the CSD that installs it. Those three paths remain manual-only.

### More invariants that span files

(These belong with the section above; they are here because the file grew in this order.)

**The binder keeps observed and permitted access apart.** A bound `file` row carries the
program's own `io` (what the module does) AND `permittedIo` (what the region allows).
Overwriting the first with the second makes every read-only module look like an updater;
dropping the second loses "permitted update, never updated", which is a finding. The same
rule as `_PERMITTED` on the unbound row, at the other end of the join.

**An unbound row is not automatically a gap.** A program names both a MAPSET and the MAP
inside it, and only the mapset is ever a CSD resource - so `terminal-map CUSTM02`
unresolved is the CORRECT answer, not a missing definition. Every unbound row carries a
reason saying which it is, because a consumer counting unbound rows as gaps would report a
correct run as a broken one. Same for a program under AUTOINSTALL.

**One edge table, five syntaxes.** `csd.build_references` is called by the CSD parser, by
`bas.py` and by `bundles.py`; `tables.py` calls its own with `Attr.macro_field()`. A BAS
`TRANDEF`'s `PROGRAM`, a `DFHPCT TYPE=ENTRY,PROGRAM=` and a `DEFINE TRANSACTION ...
PROGRAM()` must produce an identical manifest row, or keeping one table has no point.

**A continuation mark must be in column 72 exactly.** A mark in column 74 continues
nothing: the statement ends, the next line is read as a fresh one, its operation is not a
known macro, and every operand on it disappears without a word. This repository's own first
draft of `legacy.pct` had that bug, which is why `lexer.lex_macro` FLAGS content past
column 72 when column 72 is blank, why the column-sensitive examples are generated by
`tools/make_examples.py`, and why `test_examples.py` asserts the property against the bytes
as well as against the generator.

**A verb is the leading run of name characters, not everything up to the first blank.** A
BATCHREP `CONTEXT(EYUPLX01)` has no blank in it. Split on one, the verb becomes
`CONTEXT(EYUPLX01)` and matches nothing. The related rule - a command verb followed by `(`
is an operand - exists because `ADD`, `DELETE` and `LIST` are CSD attribute keywords too;
it does NOT apply to BAS, where `CONTEXT` and `SCOPE` are genuinely written that way, hence
`lex_csd`'s `paren_commands`.

**BMS is the only field level, and a mapset is not a CSD resource.** `DFHMSD TYPE=DSECT`
generates `CUSTNOL`/`CUSTNOF`/`CUSTNOA`/`CUSTNOI`/`CUSTNOO` from a field `CUSTNO`, which is
mechanical and joinable to COBOL data names. An unnamed `DFHMDF` is a screen literal and
generates nothing - reporting five data names for it would invent five COBOL fields. And
`bms.parse_bms` returns mapsets rather than a Region: the `DEFINE MAPSET` is the CSD
resource, the mapset is a screen layout, and mixing them puts a layout in the manifest as
though the CSD had declared it.

**A macro table and a BAS deck cannot be decided by the install closure.** A macro table
has no GROUP and no LIST - what makes it live is the SIT naming its suffix. A BAS resource
is installed by a RESDESC. Both say so on the resource rather than reporting
`defined-not-installed`, which would read as "nothing installs this".

**A DDNAME is not a dataset.** A TDQUEUE's `DDNAME` edge is kind **`file`** - the family's
kind for a name awaiting a dataset, exactly as the COBOL and assembler sides use it for a
ddname - and only `bind_jcl_region` turns it into a `dataset`. Emitted as `dataset` it
produced rows like `dataset INREADER`, which reads as a catalogued dataset of that name and
joins to nothing. The real region JCL is what exposed this; no synthetic fixture would
have.

**A DD that matches nothing is a finding, not an error.** It is either a macro-era file
whose deck was not supplied, or dead JCL, and the row says so. Likewise a DD that
disagrees with a `DEFINE FILE` DSNAME: both are reported, neither wins - the same rule as
the two-eras conflict, for the same reason.

**`Region.jcl is None` and an empty binding are different statements.** "No startup job was
supplied" is not "the job binds nothing", and an estate report that conflated them would
read as a region with no files.

**The peer fixtures are produced, never written.**
`tests/fixtures/custinq.asm.artifacts.json` comes from actually running
`asm-dependencies` over its own `examples/custinq.asm`, and
`tests/fixtures/cicsapp1.jcl.lineage.json` from running `jcl-dependencies` over this
repo's `examples/cicsapp1.jcl` (`tools/refresh_fixture.py --record` does both). A
hand-written fixture passes forever while the real shape drifts underneath, and the drift
is silent: a manifest nobody managed to bind looks exactly like one nobody tried to bind.
`--check` runs in the suite and asserts each binder still finds what it reads - including
that a `ddBinding` still names `DFHSIP`, since the region's DDs are found by the step's
program and a renamed key binds nothing without failing.

## Output is the contract

Every byte of both views is output. Key order, list order, the presence of a `needs`, the
wording of a flag - none of it is asserted by the suite, so `tools/byteproof.py` is what
actually guards it. Each example deck is hashed **twice for the SIT**: without one every
resource is `installed: unknown`, with one they are decided, and those are genuinely
different outputs that a change collapsing them would otherwise hide. The SIT is this
package's `&SYSPARM`.

`examples/` is NOT the validation - `corpus/` is. An example proves only that the tool does
what it was built to do. The CSD decks there are hand-written, which is safe because CSD
syntax is free-form; `legacy.pct` and `lgmap.bms` are **generated** by
`tools/make_examples.py`, because hand-spacing a column-72 continuation does not survive
editing and its failure is silent.

`examples/legacy.csd` exists solely to collide with `appregn.csd`: the two-eras conflict
rule lives entirely in output wording and has no other guard.

`.gitattributes` pinning `eol=lf` is load-bearing here, not cosmetic - a CRLF checkout
changes every hashed byte.

## Honesty discipline

Nothing is guessed. Anything unresolved is surfaced: a group named by a LIST that is not in
hand, a `REMOTESYSTEM` pointing at another region, a TSMODEL that matched by prefix, a
COMMAREA whose layout is a convention, a transaction with no `PROGRAM` because it is
routed, a security profile that lives in RACF and not here. When adding a feature, the
question to answer is "what does this tool *not* know here, and does the output say so?"

## What is left

The build order is done and four of the six paths have real source behind them. What
remains is not code:

1. **A CICSPlex SM `BATCHREP` deck and a CICS bundle with its CSD.** The only two paths
   still written purely from the manuals. Every other path gave up defects the moment real
   source arrived - an HLASM remark, a `USAGE=MAP` mapset, a JCL-wrapped deck, a non-IBM
   macro prefix - and there is no reason these two are different.
2. **A paginated `DFHCSDUP EXTRACT` REPORT**, as opposed to the DEFINE-shaped extract
   CardDemo is. `detect.py` does not recognise it, and reading one as a deck loses rows
   silently rather than failing.
3. **A CSD-era SIT.** KICKS's SIT is real but macro-era and has no `GRPLIST`, so the
   install closure is still exercised only against fixtures written here.
4. **Register the fourteen kinds upstream** once a corpus run shows which of them actually
   appear often enough to be worth fetching. `tests/test_resources.py` goes red the day any
   of them lands in `mainframe_artifacts.fetch._KIND_TYPE`.
