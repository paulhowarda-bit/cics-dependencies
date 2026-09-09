"""What a parsed CICS definition source is, before any view is projected from it.

Every parser in this package - CSD deck, EXTRACT report, table macro deck, BATCHREP,
bundle - produces these objects and nothing else, which is what lets one manifest shape
come out of five different syntaxes and three decades.

Nothing here knows about JSON. Nothing here decides evidence, either: the parsers set it
from what the syntax stated, and ``views.py`` reports it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

# --------------------------------------------------------------------------- #
# vocabularies that are output, so they are named once
# --------------------------------------------------------------------------- #

#: How well the name on an edge is known. Same axis as asm-dependencies' ``evidence``,
#: narrowed to what a declarative definition can produce.
EVIDENCE_LITERAL = "literal"      # the name is written in the definition
EVIDENCE_PREFIX = "prefix"        # a TSMODEL PREFIX match, not an equality
EVIDENCE_GENERIC = "generic"      # a wildcard/generic name in the definition
EVIDENCE_DYNAMIC = "dynamic"      # named at run time; nothing in the source says it

#: Whether the resource is live in a region. A DIFFERENT question from evidence: a
#: perfectly known definition in a group nothing installs is both.
INSTALLED_YES = "installed"
INSTALLED_NO = "defined-not-installed"
INSTALLED_UNKNOWN = "unknown"     # no SIT in hand - the honest default, not a failure

#: Where a definition came from. Carried per resource because a region is routinely
#: assembled from several sources at once, and "which era said this" is the first
#: question asked of a surprising row.
SOURCE_CSD = "csd"                # a DFHCSDUP DEFINE deck
SOURCE_EXTRACT = "csd-extract"    # DFHCSDUP EXTRACT/LIST report output
SOURCE_MACRO = "macro-table"      # DFHPCT/DFHPPT/DFHFCT/... assembler deck
SOURCE_SIT = "sit"                # DFHSIT source or a SIT override
SOURCE_BAS = "bas"                # CICSPlex SM BATCHREP
SOURCE_BUNDLE = "bundle"          # META-INF/cics.xml and its parts


# --------------------------------------------------------------------------- #
# one edge, established
# --------------------------------------------------------------------------- #

@dataclass
class Reference:
    """One artifact named by one attribute of one resource.

    The ``Attr`` in ``resources.ATTRIBUTES`` says such an edge is POSSIBLE; a
    ``Reference`` says it was actually written, with the value, and where.
    """

    field: str                    # the attribute keyword, as the source spelt it
    name: str                     # the value - the artifact's name
    kind: str                     # artifact kind, from the Attr
    relation: str                 # what the edge means, from the Attr
    evidence: str = EVIDENCE_LITERAL
    io: Optional[str] = None      # permitted access, for file-like kinds only
    line: Optional[int] = None
    note: str = ""


# --------------------------------------------------------------------------- #
# one definition
# --------------------------------------------------------------------------- #

@dataclass
class Resource:
    """One defined CICS resource: a TRANSACTION, a FILE, a TDQUEUE, a PROGRAM...

    ``attributes`` keeps EVERY attribute the source gave, edge-bearing or not, because a
    TWASIZE or a RECOVERY status is not a dependency but is very often the reason someone
    is reading the manifest at all.
    """

    kind: str                                  # CSD resource type, upper case
    name: str
    group: Optional[str] = None                # CSD GROUP, or the BAS RESGROUP
    attributes: Dict[str, str] = field(default_factory=dict)
    references: List[Reference] = field(default_factory=list)
    source: str = SOURCE_CSD
    source_name: str = "<csd>"
    line: Optional[int] = None
    installed: str = INSTALLED_UNKNOWN
    flags: List[str] = field(default_factory=list)

    def key(self):
        """Identity within a region. A resource kind and a name - the group is where it
        is DEFINED, not part of what it IS, and the same name in two groups is a real
        conflict this key is meant to expose rather than hide."""
        return (self.kind, self.name)


@dataclass
class GroupDef:
    """A CSD GROUP: the unit that gets installed, and the unit a LIST names."""

    name: str
    lists: List[str] = field(default_factory=list)   # LISTs that ADD this group
    source_name: str = "<csd>"


@dataclass
class ListDef:
    """A CSD LIST: an ordered set of groups. The SIT's GRPLIST names lists, lists name
    groups, and that two-step closure is the whole of what "installed" means."""

    name: str
    groups: List[str] = field(default_factory=list)  # in ADD order, which is install order
    source_name: str = "<csd>"


# --------------------------------------------------------------------------- #
# the assembled subject
# --------------------------------------------------------------------------- #

@dataclass
class Region:
    """Everything one analysis knows: the definitions, the group/list structure, and -
    when a SIT was supplied - which of it is actually live.

    A Region with no SIT is a perfectly normal result. Every resource in it carries
    ``installed = unknown`` and the flags say why, which is the honest reading of a CSD
    handed over without the region that runs it.
    """

    applid: Optional[str] = None
    sysidnt: Optional[str] = None
    grplist: List[str] = field(default_factory=list)   # SIT GRPLIST
    sit: Dict[str, str] = field(default_factory=dict)  # every SIT parameter, verbatim

    resources: List[Resource] = field(default_factory=list)
    groups: Dict[str, GroupDef] = field(default_factory=dict)
    lists: Dict[str, ListDef] = field(default_factory=dict)

    sources: List[str] = field(default_factory=list)   # every source that fed this region
    flags: List[str] = field(default_factory=list)

    #: What the region's startup job said, once ``views.bind_jcl_region`` has read one:
    #: CICS's own datasets, the file names it bound, and the DDs that matched nothing.
    #: ``None`` until then, which is different from an empty binding and is reported as
    #: such - "no startup job was supplied" and "the job binds nothing" are not the same
    #: statement about an estate.
    jcl: Optional[dict] = None

    #: The three-letter prefix this region's macros use. ``DFH`` is IBM's; a KICKS region
    #: uses ``KIK``, and a shop that wraps IBM's macros uses its own. It decides what the
    #: SIT's table suffixes NAME: ``FCT=DO`` under a ``KIKSIT`` means the member
    #: ``KIKFCTDO``, and asking the estate for ``DFHFCTDO`` gets a not-found that is about
    #: this package rather than about the estate.
    macro_prefix: str = "DFH"

    def by_kind(self, kind: str) -> List[Resource]:
        """Every resource of one kind, in definition order."""
        k = kind.upper()
        return [r for r in self.resources if r.kind == k]
