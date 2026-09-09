"""CICS bundles -> Resource objects.

A bundle directory's ``META-INF/cics.xml`` lists ``<define>`` entries, each naming a
resource type by namespace URI and pointing at a bundle part that carries the attributes:

    <define name="LGMN" type="http://www.ibm.com/xmlns/prod/cics/bundle/TRANSACTION"
            path="LGMN.transaction"/>

The type is read from the LAST path segment of the URI, not by matching the whole string:
the namespace host and version have changed across CICS releases, and a parser keyed on the
full URI silently stops recognising anything the day a site upgrades.

Two things kept honest:

**A ``DEFINE BUNDLE(...) BUNDLEDIR(...)`` in the CSD is a pointer to a SECOND definition
source, not a leaf.** A region whose bundle directories were never read has resources it
cannot see, and that gap is flagged rather than left as an absence.

**A bundle lives on zFS, outside the estate's member service.** So the parts are supplied
by a resolver the caller provides; an unreadable one is reported with its path, never
treated as empty.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Callable, Dict, List, Optional

from .csd import build_references
from .model import Region, Resource, SOURCE_BUNDLE
from .resources import RESOURCE_TYPES

#: A bundle part's own root element carries the attributes, in lower case
#: (``<transaction name="LGMN" program="LGMENU"/>``). Uppercased to meet the one
#: attribute vocabulary the rest of the package uses.
PartResolver = Callable[[str], Optional[str]]


def _type_tail(uri: Optional[str]) -> Optional[str]:
    if not uri:
        return None
    return uri.rstrip("/").rsplit("/", 1)[-1].upper() or None


def _part_attributes(text: str) -> Dict[str, str]:
    root = ET.fromstring(text)
    return {key.upper(): (value or "") for key, value in root.attrib.items()}


def parse_bundle(manifest_xml: str, *, source_name: str = "<cics.xml>",
                 part: Optional[PartResolver] = None,
                 region: Optional[Region] = None) -> Region:
    """Parse a bundle manifest (and, where a resolver supplies them, its parts).

    ``part(path) -> text | None`` reads one bundle part. Without it the manifest still
    yields every resource the bundle DEFINES - the names and types are in the manifest -
    and each row says its attributes were not read, which is a smaller and differently
    shaped gap from the resource being absent.
    """
    region = region if region is not None else Region()
    region.sources.append(source_name)

    try:
        root = ET.fromstring(manifest_xml)
    except ET.ParseError as exc:
        region.flags.append(
            "%s: this is not readable XML (%s), so no bundle resource was modelled - "
            "which is not the same as the bundle being empty" % (source_name, exc))
        return region

    defines = [el for el in root.iter() if el.tag.rsplit("}", 1)[-1] == "define"]
    if not defines:
        region.flags.append(
            "%s: no <define> elements, so this bundle declares no CICS resources"
            % source_name)
        return region

    unmodelled: List[str] = []
    for el in defines:
        kind = _type_tail(el.get("type"))
        name = el.get("name")
        path = el.get("path")
        if kind is None or name is None:
            region.flags.append(
                "%s: a <define> has no %s and was skipped"
                % (source_name, "type" if kind is None else "name"))
            continue
        if kind not in RESOURCE_TYPES:
            unmodelled.append("%s (%s)" % (name, kind))
            continue

        attrs: Dict[str, str] = {}
        note = None
        if part is not None and path:
            text = part(path)
            if text is None:
                note = ("the bundle part %s could not be read, so this resource's "
                        "attributes - including anything it depends on - are unknown"
                        % path)
            else:
                try:
                    attrs = _part_attributes(text)
                except ET.ParseError as exc:
                    note = "the bundle part %s is not readable XML (%s)" % (path, exc)
        elif path:
            note = ("no bundle-part resolver was supplied, so %s was not read: this "
                    "resource is known to exist and its attributes are not" % path)

        res = Resource(kind=kind, name=name, group=None, attributes=attrs,
                       source=SOURCE_BUNDLE, source_name=source_name)
        res.references = build_references(kind, attrs, {})
        res.flags.append(
            "declared by a CICS bundle; a bundle is installed by its BUNDLE definition, "
            "not by a CSD GRPLIST, so this package's install closure cannot decide it")
        if note:
            res.flags.append(note)
        region.resources.append(res)

    if unmodelled:
        region.flags.append(
            "%s declares %d resource(s) of types this package does not model: %s"
            % (source_name, len(unmodelled), ", ".join(sorted(unmodelled))))
    return region


def bundle_directories(region: Region) -> List[dict]:
    """Every ``BUNDLEDIR`` a CSD ``DEFINE BUNDLE`` names, as a list of gaps to close.

    Reported so a run can say what it did NOT read. A bundle directory nobody supplied is
    a set of resources missing from the model, and the manifest should not read as though
    the region simply had none.
    """
    out = []
    for res in region.by_kind("BUNDLE"):
        directory = res.attributes.get("BUNDLEDIR")
        if directory:
            out.append({"bundle": res.name, "bundledir": directory,
                        "source": res.source_name, "line": res.line,
                        "reason": "a bundle directory is a second definition source; "
                                  "resources it declares are absent from this model "
                                  "until its META-INF/cics.xml is parsed"})
    return out
