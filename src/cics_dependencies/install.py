"""Which definitions are actually live.

The closure is two steps and no more: the SIT's ``GRPLIST`` names LISTs, a LIST names
GROUPs in ADD order, and a resource is installed exactly when its group is reached.

Three states, and the third is the interesting one:

``installed``               the group is reached from GRPLIST
``defined-not-installed``   the DEFINE exists and nothing installs it
``unknown``                 no SIT in hand

``unknown`` is the honest default, not a failure. Defaulting to installed inflates a dead
estate by however many groups it has accumulated over thirty years; defaulting to
not-installed hides live resources. Both are wrong in a way no flag would make visible,
because the manifest would look complete either way.

Two things this can never see, and both are flagged rather than modelled: a resource
installed at run time by ``CEDA INSTALL`` or ``CEMT``, and one created by ``EXEC CICS
CREATE`` from a program. Neither leaves a trace in any definition source.
"""

from __future__ import annotations

from typing import List, Set, Tuple

from .classify import is_ibm_group
from .model import INSTALLED_NO, INSTALLED_UNKNOWN, INSTALLED_YES, Region

#: Said once, so the manifest and any summary word it identically.
RUNTIME_INSTALL_CAVEAT = (
    "a resource can also be installed at run time by CEDA INSTALL or CEMT, or created by "
    "EXEC CICS CREATE - neither leaves a trace in any definition source, so "
    "'defined-not-installed' means 'nothing in these sources installs it', not 'not "
    "running'")


def installed_groups(region: Region) -> Tuple[Set[str], List[str]]:
    """The groups GRPLIST reaches, and the flags raised getting there.

    A LIST named by GRPLIST that is not in hand is the stage-1 retrieval trigger, and it
    is reported with what it costs: every group in it, and so every resource in those
    groups, is unaccounted for.
    """
    reached: Set[str] = set()
    flags: List[str] = []

    for name in region.grplist:
        lst = region.lists.get(name)
        if lst is None:
            if is_ibm_group(name):
                flags.append(
                    "GRPLIST names the IBM-supplied list %s, which is not in these "
                    "sources - expected, since it holds CICS's own definitions rather "
                    "than the shop's" % name)
            else:
                flags.append(
                    "GRPLIST names the list %s, which is not in these sources - every "
                    "group it adds, and every resource in them, is unaccounted for "
                    "here" % name)
            continue
        for group in lst.groups:
            reached.add(group)

    return reached, flags


def apply_install_state(region: Region) -> Region:
    """Set ``installed`` on every resource in ``region``. Mutates and returns it.

    Idempotent, and safe to call before a SIT arrives: with no GRPLIST every resource
    keeps ``unknown`` and one flag says why, rather than sixty rows each saying it.
    """
    if not region.grplist:
        for res in region.resources:
            res.installed = INSTALLED_UNKNOWN
        region.flags.append(
            "no SIT GRPLIST was supplied, so every resource is reported "
            "'installed: unknown'. Supply the region's SIT to decide it")
        return region

    reached, flags = installed_groups(region)
    region.flags.extend(flags)

    orphaned = 0
    for res in region.resources:
        if res.group and res.group in reached:
            res.installed = INSTALLED_YES
        else:
            res.installed = INSTALLED_NO
            orphaned += 1

    if orphaned:
        region.flags.append(
            "%d of %d definitions are in no group that GRPLIST reaches (%s)"
            % (orphaned, len(region.resources), RUNTIME_INSTALL_CAVEAT))
    return region
