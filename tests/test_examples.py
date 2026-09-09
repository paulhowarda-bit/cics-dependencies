"""The generated examples must match their generator.

``legacy.pct`` and ``lgmap.bms`` are column-sensitive: HLASM continues a statement only
when column 72 - column 72 exactly - is non-blank. The first draft of ``legacy.pct`` was
hand-spaced and had its mark in column 74, which continues nothing and silently loses every
operand on the next line. So they are generated, and this fails if the committed files
drift from what the generator produces.
"""

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_the_generated_examples_have_not_drifted():
    proc = subprocess.run([sys.executable, str(REPO / "tools" / "make_examples.py"),
                           "--check"], capture_output=True, text=True, cwd=str(REPO))
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_every_continuation_mark_is_in_column_72():
    """The property the generator exists to guarantee, asserted against the bytes rather
    than against the generator - so a file edited by hand fails here even if someone also
    edited the generator to match."""
    for path in sorted((REPO / "examples").glob("*.pct")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.startswith("*"):
                continue
            past = line[72:].rstrip()
            assert not past, (
                "%s line %d has content past column 72 (%r) - a continuation mark there "
                "continues nothing" % (path.name, number, past))
