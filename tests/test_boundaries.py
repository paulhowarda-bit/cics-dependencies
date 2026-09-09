"""This package must never depend on the COBOL, JCL, Easytrieve or assembler ones.

The five are peers: the COBOL tools say what a program does, the JCL one says which
dataset a batch ddname is, the Easytrieve one says which bytes become which, the
assembler one says what a module calls, and this one says what the region wires those
names to. They meet at plain dicts. Nothing about the source layout enforces that - a
single stray import would erase it while every other test still passed, and the cost is
not abstract: a CICS box would start carrying a COBOL modelling engine it never executes,
and this repository could no longer be released on its own.

A note on how, because getting it wrong is easy and silent: ``sys.meta_path`` finders are
consulted through ``find_spec``. ``find_module`` was REMOVED in Python 3.12, so a blocker
that only defines it is ignored entirely and every test here passes vacuously.
"""

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from _mainframe_common import CHECKOUT

SRC = Path(__file__).resolve().parents[1] / "src"
# The child interpreters cannot inherit conftest's sys.path insertion, so they get the same
# trees explicitly: this repo's src plus the sibling checkout's mainframe-artifacts (a
# nonexistent path is inert - the pip-installed distribution carries the run then).
_TREES = (str(CHECKOUT / "mainframe-artifacts" / "src"), str(SRC))

_BLOCKED = ("cobol_xstate", "cobol_parser", "jcl_dependencies", "eztrieve_dependencies",
            "asm_dependencies")

#: Every module in the package. Hand-maintained on purpose - a new module missing from
#: here is silently unchecked, so adding one is meant to make this list fail first.
_MODULES = ["__init__", "__main__", "api", "bas", "bms", "bundles", "classify", "cli",
            "csd", "detect", "install", "lexer", "model", "prefetch", "resources", "sit",
            "tables", "views"]

_PREAMBLE = textwrap.dedent("""
    import sys
    for _tree in %r:
        sys.path.insert(0, _tree)

    class Blocker:
        def find_spec(self, name, path=None, target=None):
            if name.split(".")[0] in %r:
                raise ImportError("BLOCKED " + name)
            return None

    sys.meta_path.insert(0, Blocker())
""")


def _isolated(body):
    """A fresh interpreter: blocking a module already in sys.modules does nothing."""
    return subprocess.run([sys.executable, "-c",
                           _PREAMBLE % (_TREES, _BLOCKED) + textwrap.dedent(body)],
                          capture_output=True, text=True)


@pytest.mark.parametrize("package", _BLOCKED)
def test_the_blocker_actually_blocks(package):
    """Guard the guard. If this passes when it should not, everything below is vacuous."""
    proc = _isolated("import {0}".format(package))
    assert proc.returncode != 0
    assert "BLOCKED {0}".format(package) in proc.stderr


def test_the_package_works_with_the_sibling_packages_unavailable():
    proc = _isolated("""
        from cics_dependencies.api import analyze
        a = analyze([("t.csd",
                      " DEFINE TRANSACTION(APMN) GROUP(G) PROGRAM(APPMENU)\\n")],
                    retrieve=False)
        names = [r["artifact"] for r in a.artifacts()["artifacts"]]
        assert names == ["APPMENU"], names
        assert a.artifacts()["provides"][0]["name"] == "APMN"
        print("OK")
    """)
    assert proc.returncode == 0, proc.stderr
    assert "OK" in proc.stdout


def test_the_cli_works_with_the_sibling_packages_unavailable(tmp_path):
    proc = _isolated("""
        import io, contextlib, os
        from cics_dependencies.cli import run
        out = {out!r}
        with contextlib.redirect_stderr(io.StringIO()):
            rc = run([{src!r}, "--outdir", out, "-q", "--no-fetch"])
        assert rc == 0, rc
        print("FILES", len([f for f in os.listdir(out) if f.endswith(".json")]))
    """.format(out=str(tmp_path / "o"),
               src=str(SRC.parent / "examples" / "appregn.csd")))
    assert proc.returncode == 0, proc.stderr
    assert "FILES 4" in proc.stdout       # both views + both retrieval reports


def test_the_jcl_join_takes_a_dict_and_needs_no_jcl_types():
    """bind_jcl_region is the one function that serves a JCL feature. It consumes a plain
    lineage dict, which is precisely what keeps that dependency from existing."""
    proc = _isolated("""
        import json, pathlib
        from cics_dependencies.csd import parse_csd
        from cics_dependencies.views import bind_jcl_region
        lineage = json.loads(pathlib.Path({fixture!r}).read_text(encoding="utf-8"))
        region = parse_csd(pathlib.Path({src!r}).read_text(encoding="utf-8"),
                           source_name="appregn.csd")
        bind_jcl_region(region, lineage)
        row = next(b for b in region.jcl["bound"] if b["ddname"] == "CUSTMAS")
        print("DATASET", row["dataset"])
    """.format(fixture=str(SRC.parent / "tests" / "fixtures"
                           / "cicsapp1.jcl.lineage.json"),
               src=str(SRC.parent / "examples" / "appregn.csd")))
    assert proc.returncode == 0, proc.stderr
    assert "DATASET PROD.CUSTOMER.MASTER" in proc.stdout


@pytest.mark.parametrize("module", _MODULES)
def test_no_module_imports_a_sibling_package(module):
    """Read the source too: an import inside a rarely-taken branch would not show up in a
    passing import test."""
    src = (SRC / "cics_dependencies" / "{0}.py".format(module)).read_text(encoding="utf-8")
    for line in src.splitlines():
        s = line.strip()
        if s.startswith(("import ", "from ")):
            for blocked in _BLOCKED:
                assert ("{0}.".format(blocked) not in s
                        and s != "import {0}".format(blocked)
                        and not s.startswith("from {0} ".format(blocked))), (
                    "cics_dependencies/{0}.py imports {1}: {2}".format(
                        module, blocked, s))


def test_the_module_inventory_is_complete():
    """The parametrize list above is hand-maintained, so a module added without being
    listed would be silently unchecked. This is what makes that a red test."""
    on_disk = sorted(p.stem for p in (SRC / "cics_dependencies").glob("*.py"))
    assert on_disk == sorted(_MODULES)
