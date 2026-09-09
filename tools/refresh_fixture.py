#!/usr/bin/env python3
"""Regenerate (or verify) this repository's half of the cross-repo binder contracts.

Two binders, two peers, two committed fixtures - each produced by ACTUALLY RUNNING the
peer, never written by hand:

``tests/fixtures/custinq.asm.artifacts.json``
    an ``asm-dependencies`` manifest for its own ``examples/custinq.asm``. What
    ``bind_program_artifacts`` closes.

``tests/fixtures/cicsapp1.jcl.lineage.json``
    a ``jcl-dependencies`` lineage view of THIS repository's ``examples/cicsapp1.jcl``,
    the CICS region startup job. What ``bind_jcl_region`` reads - and on a macro-era
    estate the only place a file name is bound to a dataset.

A hand-written fixture passes forever while the real shape drifts underneath it, and the
drift does not fail loudly: a manifest nobody managed to bind looks EXACTLY like one nobody
tried to bind - same rows, same kinds, just no ``definition`` key. So ``--check`` runs in
the suite and asserts the shape each binder actually reads.

    python tools/refresh_fixture.py --record   # re-run both peers, rewrite both fixtures
    python tools/refresh_fixture.py --check    # assert the committed shapes
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import List

REPO = Path(__file__).resolve().parents[1]
FIXTURES = REPO / "tests" / "fixtures"
COMMON = REPO.parent / "mainframe-common" / "mainframe-artifacts" / "src"

ASM_REPO = Path(os.environ.get("ASM_DEPENDENCIES_REPO", REPO.parent / "asm-dependencies"))
JCL_REPO = Path(os.environ.get("JCL_DEPENDENCIES_REPO", REPO.parent / "jcl-dependencies"))

#: The row kinds ``bind_program_artifacts`` resolves. A peer that stopped emitting one
#: would silently halve the binder's usefulness, so the shape check names them.
BOUND_KINDS = ("cics-transaction", "file", "queue", "terminal-map", "program")

#: The ddnames ``bind_jcl_region`` needs to find in the lineage view.
BOUND_DDNAMES = ("DFHRPL", "DFHCSD", "CUSTMAS", "APPRPT")

_ASM_SCRIPT = textwrap.dedent("""
    import json, sys
    from pathlib import Path
    from asm_dependencies.api import analyze
    src = Path(sys.argv[1]).read_text(encoding="utf-8")
    print(json.dumps(analyze(src, source_name="custinq.asm",
                             retrieve=False).artifacts(), indent=2))
""")

_JCL_SCRIPT = textwrap.dedent("""
    import json, sys
    from pathlib import Path
    from jcl_dependencies.api import analyze
    src = Path(sys.argv[1]).read_text(encoding="utf-8")
    print(json.dumps(analyze(src, source_name="cicsapp1.jcl",
                             retrieve=False).lineage(), indent=2))
""")


def _run_peer(repo: Path, script: str, argument: Path, out: Path, label: str) -> int:
    if not repo.is_dir():
        print("error: no %s checkout at %s" % (label, repo))
        return 2
    env = dict(os.environ)
    sep = ";" if os.name == "nt" else ":"
    env["PYTHONPATH"] = sep.join(
        [str(repo / "src"), str(COMMON), env.get("PYTHONPATH", "")])
    proc = subprocess.run([sys.executable, "-c", script, str(argument)],
                          capture_output=True, text=True, cwd=str(repo), env=env)
    if proc.returncode != 0:
        print("error: the %s run failed:\n%s" % (label, proc.stderr))
        return 1
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(proc.stdout.rstrip("\n") + "\n", encoding="utf-8", newline="\n")
    print("recorded %s (%d bytes) from %s" % (out.name, out.stat().st_size, label))
    return 0


def record() -> int:
    rc = _run_peer(ASM_REPO, _ASM_SCRIPT, ASM_REPO / "examples" / "custinq.asm",
                   FIXTURES / "custinq.asm.artifacts.json", "asm-dependencies")
    rc = _run_peer(JCL_REPO, _JCL_SCRIPT, REPO / "examples" / "cicsapp1.jcl",
                   FIXTURES / "cicsapp1.jcl.lineage.json", "jcl-dependencies") or rc
    return rc


def _check_asm(problems: List[str]) -> int:
    path = FIXTURES / "custinq.asm.artifacts.json"
    if not path.is_file():
        problems.append("no fixture at %s" % path)
        return 0
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if not manifest.get("program"):
        problems.append("the asm manifest has no 'program' key - the peer's subject name")
    rows = manifest.get("artifacts") or []
    if not rows:
        problems.append("the asm manifest's 'artifacts' is missing or empty")
    for row in rows:
        if "artifact" not in row or "kind" not in row:
            problems.append("an asm row lacks 'artifact' or 'kind': %r" % row)
            break
    missing = [k for k in BOUND_KINDS if k not in {r.get("kind") for r in rows}]
    if missing:
        problems.append(
            "the asm fixture no longer exercises every kind bind_program_artifacts "
            "resolves; missing %s" % ", ".join(missing))
    return len(rows)


def _check_jcl(problems: List[str]) -> int:
    path = FIXTURES / "cicsapp1.jcl.lineage.json"
    if not path.is_file():
        problems.append("no fixture at %s" % path)
        return 0
    lineage = json.loads(path.read_text(encoding="utf-8"))
    bindings = lineage.get("ddBindings")
    if not isinstance(bindings, list) or not bindings:
        problems.append("the JCL lineage has no 'ddBindings' - the only key this reads")
        return 0
    for binding in bindings:
        for key in ("program", "ddname"):
            if key not in binding:
                problems.append("a ddBinding lacks '%s': %r" % (key, binding))
                break
    if not any(b.get("program") == "DFHSIP" for b in bindings):
        problems.append(
            "no ddBinding names DFHSIP - bind_jcl_region finds the region's DDs by the "
            "step's program, so a renamed key or a changed program name silently binds "
            "nothing")
    missing = [d for d in BOUND_DDNAMES if d not in {b.get("ddname") for b in bindings}]
    if missing:
        problems.append("the JCL fixture no longer carries the ddnames the binder is "
                        "tested on; missing %s" % ", ".join(missing))
    return len(bindings)


def check() -> int:
    problems: List[str] = []
    rows = _check_asm(problems)
    bindings = _check_jcl(problems)
    if problems:
        print("FIXTURE CONTRACT FAILURE (%d):" % len(problems))
        for problem in problems:
            print("  " + problem)
        print("\n  python tools/refresh_fixture.py --record")
        return 1
    print("fixture contracts intact: %d asm manifest rows, %d JCL dd bindings"
          % (rows, bindings))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--record", action="store_true",
                       help="re-run both peers and rewrite both fixtures")
    group.add_argument("--check", action="store_true",
                       help="assert the committed fixtures' shapes")
    args = parser.parse_args(argv)
    return record() if args.record else check()


if __name__ == "__main__":
    sys.exit(main())
