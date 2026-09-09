"""The ratchet has to be run to mean anything, so the suite runs it.

Twice, under two different ``PYTHONHASHSEED`` values. Nothing in the views should depend
on dict or set iteration order, but "should not" is exactly the kind of claim that decays:
a ``set`` comprehension whose result is emitted without sorting produces stable output on
one seed and different output on the next, and a single-seed ratchet records whichever it
happened to see. The sibling repositories document this as an operator's job; here it is
a test, because a documented discipline is not a guard.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
GOLDENS = REPO / "goldens" / "views.sha256"
BYTEPROOF = REPO / "tools" / "byteproof.py"

#: Two arbitrary, fixed seeds. Any two different values would do; fixing them keeps the
#: test itself deterministic.
SEEDS = ("0", "12345")


def _run(seed):
    env = dict(os.environ, PYTHONHASHSEED=seed)
    return subprocess.run([sys.executable, str(BYTEPROOF), "--check", str(GOLDENS)],
                          capture_output=True, text=True, env=env, cwd=str(REPO))


@pytest.mark.parametrize("seed", SEEDS)
def test_the_views_are_byte_stable_under_this_hash_seed(seed):
    if not GOLDENS.is_file():
        pytest.skip("no goldens recorded yet - "
                    "python tools/byteproof.py --record goldens/views.sha256")
    proc = _run(seed)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_every_example_deck_is_covered_by_the_goldens():
    """A deck added to examples/ without being hashed is silently unguarded - the same
    class of hole as a module missing from the boundary test's inventory."""
    if not GOLDENS.is_file():
        pytest.skip("no goldens recorded yet")
    recorded = GOLDENS.read_text(encoding="utf-8")
    for deck in sorted((REPO / "examples").iterdir()):
        if deck.suffix.lower() in (".csd", ".pct", ".bms"):
            assert deck.name in recorded, deck.name
