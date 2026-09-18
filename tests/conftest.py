"""Development convenience: find mainframe-artifacts and cics-parser in their sibling
checkout.

Installed (pip install), the dependencies are simply importable and none of this runs.
From a bare dual-checkout - mainframe-common beside this repo, nothing installed -
the modules that reach either would die collecting, which on a developer
machine is a wall of collection errors for no reason. So _mainframe_common.py puts the
sibling's src on sys.path, and when NEITHER is present every module except the sentinel
(test_sibling_distribution.py) is ignored, so the run ends as one clean skip naming
the exact pip command.
"""

from pathlib import Path

from _mainframe_common import ensure_on_path

_HERE = Path(__file__).resolve().parent

if ensure_on_path() is not None:
    collect_ignore = sorted(
        p.name for p in _HERE.glob("test_*.py")
        if p.name != "test_sibling_distribution.py")
