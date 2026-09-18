"""The sentinel for the mainframe-common dependencies.

When mainframe-artifacts and cics-parser are reachable (installed, or via the sibling
mainframe-common checkout), this is a real assertion that they are. When it is not, conftest.py ignores
every other module in this suite and THIS one remains, so the run ends as one clean
skip naming the exact pip command instead of a wall of collection errors.
"""

import importlib.util

import pytest

from _mainframe_common import DISTRIBUTIONS, ensure_on_path


def test_the_mainframe_common_distributions_are_reachable():
    reason = ensure_on_path()
    if reason is not None:
        pytest.skip(reason)
    for package, _ in DISTRIBUTIONS:
        assert importlib.util.find_spec(package) is not None, package
