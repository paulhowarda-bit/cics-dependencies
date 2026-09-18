"""Find mainframe-artifacts and cics-parser: installed, or in the sibling checkout.

Both of this package's dependencies ship from the mainframe-common repository.
Installed, they are simply importable. From a bare dual-checkout - that repo and this
one side by side, nothing installed - each package's src goes on sys.path. Override the
checkout location with MAINFRAME_COMMON_REPO.

Shared by conftest.py (which ignores the suite when nothing is found) and the sentinel
test module that reports the absence as ONE clean skip naming the exact pip command.
Same pattern, same names as the cobol-xstate-json, jcl-dependencies,
eztrieve-dependencies and asm-dependencies copies - every consumer should fail and
recover identically.
"""

import importlib.util
import os
import sys
from pathlib import Path

CHECKOUT = Path(os.environ.get(
    "MAINFRAME_COMMON_REPO",
    Path(__file__).resolve().parents[1].parent / "mainframe-common"))


#: (package, the mainframe-common directory its distribution lives in)
DISTRIBUTIONS = (("mainframe_artifacts", "mainframe-artifacts"),
                 ("cics_parser", "cics-parser"))


def ensure_on_path():
    """Make both packages importable if possible; return None, or why not.

    The reason string names the exact pip command, because the failure has to be
    actionable from the message alone.
    """
    for package, tree in DISTRIBUTIONS:
        if importlib.util.find_spec(package) is not None:
            continue
        src = CHECKOUT / tree / "src"
        if (src / package / "__init__.py").is_file():
            sys.path.insert(0, str(src))
            continue
        return (f"{package} is neither installed nor found in a mainframe-common "
                f"checkout at {CHECKOUT} - install both distributions with "
                f"`python -m pip install -e {CHECKOUT / 'mainframe-artifacts'} -e "
                f"{CHECKOUT / 'cics-parser'}` (or set MAINFRAME_COMMON_REPO to a "
                f"checkout)")
    return None
