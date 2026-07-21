"""
XMP Sidecar Support for Fichero.

XMP (Extensible Metadata Platform) sidecar files (.xmp) are companion files
for image formats that don't support embedded metadata (JPG, TIFF, etc.).

Standard namespaces:
  - dc: Dublin Core (title, description, creator, etc.)
  - xmp: XMP basic (metadata date, etc.)
  - photoshop: Photoshop (credit, caption, etc.)
  - Iptc4xmpCore: Contact info, location, etc.
  - Iptc4xmpExt: Extended IPTC (linked entities, etc.)
  - ficher: Fichero namespace for app-specific fields

Fichero XMP profile (ficher: namespace):
  - ficher:entityId    — Linked KnowledgeEntity ID
  - ficher:claimId    — Linked KnowledgeClaim ID
  - ficher:curationState — Claim curation state (pending/approved/rejected)
  - ficher:archiveId  — Archival identifier (call number, repository ID, etc.)
  - ficher:iiifManifest — IIIF manifest URL for the source image

Usage:
    xmp_data = parse_xmp_sidecar(Path("/photos/image.jpg"))
    if xmp_data:
        doc.metadata["xmp_title"] = xmp_data.get("dc:title")
        doc.metadata["xmp_archived_call_number"] = xmp_data.get("ficher:archiveId")
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fichero.security.xml_security import reject_xml_entities

logger = logging.getLogger(__name__)

# XMP namespaces recognized by Fichero
XMP_NAMESPACES = {
    "dc": "http://purl.org/dc/elements/1.1/",
    "xmp": "http://ns.adobe.com/xap/1.0/",
    "xmpRights": "http://ns.adobe.com/xap/1.0/rights/",
    "photoshop": "http://ns.adobe.com/photoshop/1.0/",
    "Iptc4xmpCore": "http://iptc.org/std/Iptc4xmpCore/1.0/xmlns/",
    "Iptc4xmpExt": "http://iptc.org/std/Iptc4xmpExt/2008-02-29/",
    "ficher": "https://fichero.app/xmp/1.0/",
}

# Fields Fichero reads from XMP (maps namespace:localname to our metadata key)
XMP_FIELD_MAP = {
    # Dublin Core — standard descriptive metadata
    "dc:title": "xmp_title",
    "dc:description": "xmp_description",
    "dc:creator": "xmp_creator",
    "dc:subject": "xmp_keywords",  # stored as comma-separated in our model
    "dc:rights": "xmp_rights",
    # XMP basic
    "xmp:MetadataDate": "xmp_metadata_date",
    "xmp:CreateDate": "xmp_create_date",
    "xmp:CreatorTool": "xmp_creator_tool",
    # Photoshop
    "photoshop:Credit": "xmp_credit",
    "photoshop:CaptionWriter": "xmp_caption_writer",
    "photoshop:City": "xmp_city",
    "photoshop:Country": "xmp_country",
    "photoshop:DateCreated": "xmp_date_created",
    # IPTC Core
    "Iptc4xmpCore:Location": "xmp_location",
    "Iptc4xmpCore:CountryCode": "xmp_country_code",
    "Iptc4xmpCore:CreatorContactInfo": "xmp_contact_info",
    # IPTC Extended — archival fields from the issue spec
    "Iptc4xmpExt:Repository": "xmp_repository",
    "Iptc4xmpExt:DigitalObjectID": "xmp_digital_object_id",
    "ficher:archiveId": "xmp_archive_id",
    "ficher:entityId": "xmp_entity_id",
    "ficher:claimId": "xmp_claim_id",
    "ficher:curationState": "xmp_curation_state",
    "ficher:iiifManifest": "xmp_iiif_manifest",
}

# Reverse map: our metadata key -> (namespace_prefix, local_name)
METADATA_TO_XMP = {v: k for k, v in XMP_FIELD_MAP.items()}


def xmp_sidecar_path(image_path: Path | str) -> Path | None:
    """Return the expected XMP sidecar path for an image file.

    For example:
        /photos/image.jpg  ->  /photos/image.xmp
        /archive/scan.TIFF ->  /archive/scan.xmp

    Returns None if the image path has no filename component.
    """
    path = Path(image_path)
    if not path.name:
        return None
    return path.parent / f"{path.stem}.xmp"


def parse_xmp_sidecar(image_path: Path | str) -> dict[str, Any] | None:
    """Parse an XMP sidecar file for an image.

    Looks for a sibling .xmp file (same name as image, .xmp extension).
    Returns None if no sidecar exists or parsing fails.

    Args:
        image_path: Path to the image file

    Returns:
        Dict of extracted XMP fields, or None if no sidecar found
    """
    sidecar = xmp_sidecar_path(image_path)
    if not sidecar or not sidecar.exists():
        return None

    try:
        return _parse_xmp_file(sidecar)
    except Exception as e:
        logger.warning(f"Failed to parse XMP sidecar {sidecar}: {e}")
        return None


def _parse_xmp_file(xmp_path: Path) -> dict[str, Any]:
    """Parse an XMP file and return flat field map.

    Tries python-xmp-toolkit first, falls back to regex-based parsing
    for simple sidecar files.
    """
    reject_xml_entities(xmp_path.read_bytes())

    # Try python-xmp-toolkit first (most robust)
    try:
        import libxmp

        with open(xmp_path, "rb") as f:
            xmp_data = f.read()

        xmp = libxmp.XMPMeta()
        xmp.parse_from_string(xmp_data.decode("utf-8", errors="replace"))

        return _extract_xmp_fields(xmp)
    except ImportError:
        logger.debug("python-xmp-toolkit not available, using regex fallback")
    except Exception as e:
        logger.warning(f"libxmp parse failed, falling back to regex: {e}")

    # Regex fallback: parse XML-style XMP directly
    return _parse_xmp_regex(xmp_path)


def _extract_xmp_fields(xmp) -> dict[str, Any]:
    """Extract known fields from an XMPMeta object using libxmp."""
    result: dict[str, Any] = {}

    for xpath, metadata_key in XMP_FIELD_MAP.items():
        try:
            # Handle array types (e.g., dc:subject, dc:creator)
            if ":" in xpath:
                ns, local = xpath.split(":", 1)
                namespace = XMP_NAMESPACES.get(ns, "")
                if not namespace:
                    continue

                # Check if array
                prop = xmp.get_property(namespace, local)
                if prop is None:
                    # Try array
                    arr = []
                    xmp.get_array_items(namespace, local, arr)
                    if arr:
                        result[metadata_key] = arr if ns in ("dc",) else ", ".join(arr)
                else:
                    result[metadata_key] = prop
            else:
                result[metadata_key] = xmp.get_property("", xpath)
        except Exception:
            continue  # Field not present or error reading

    return result


def _parse_xmp_regex(xmp_path: Path) -> dict[str, Any]:
    """Regex-based XMP parsing for when libxmp is unavailable.

    Handles the common case of rdf:RDF/rdf:Description XMP serialized as XML.
    This is a best-effort parser that handles the fields Fichero uses.
    """

    result: dict[str, Any] = {}
    content = xmp_path.read_text(encoding="utf-8", errors="replace")

    for xpath, metadata_key in XMP_FIELD_MAP.items():
        if ":" not in xpath:
            continue
        ns_prefix, local_name = xpath.split(":", 1)
        namespace = XMP_NAMESPACES.get(ns_prefix)
        if not namespace:
            continue

        # Escape for regex
        local_escaped = re.escape(local_name)

        # Match XML attribute or element form
        # Attribute form: <rdf:Description xmlns:dc="..." dc:title="value" ...>
        attr_pattern = rf'\s{re.escape(ns_prefix)}:{local_escaped}="([^"]*)"'
        m = re.search(attr_pattern, content)
        if m:
            result[metadata_key] = m.group(1)
            continue

        # Element form: <dc:title><rdf:Alt>...<rdf:li>value</rdf:li>...</rdf:Alt></dc:title>
        # Capture simple text content
        elem_pattern = rf"<{re.escape(ns_prefix)}:{local_escaped}(?:\s[^>]*)?>([^<]*)</{re.escape(ns_prefix)}:{local_escaped}>"
        m = re.search(elem_pattern, content)
        if m:
            result[metadata_key] = m.group(1).strip()
            continue

        # Array form: <dc:subject><rdf:Bag><rdf:li>...</rdf:li>...</rdf:Bag></dc:subject>
        arr_pattern = rf"<{re.escape(ns_prefix)}:{local_escaped}(?:\s[^>]*)?>.*?</{re.escape(ns_prefix)}:{local_escaped}>"
        m = re.search(arr_pattern, content, re.DOTALL)
        if m:
            arr_content = m.group(0)
            items = re.findall(r"<rdf:li[^>]*>([^<]*)</rdf:li>", arr_content)
            if items:
                result[metadata_key] = ", ".join(i.strip() for i in items if i.strip())

    return result


def apply_xmp_to_document(
    doc: "Document",
    xmp_data: dict[str, Any],
) -> "Document":
    """Apply parsed XMP data to a Document's metadata.

    Merges XMP fields into doc.metadata without overwriting existing
    values (existing values take precedence for conflict resolution).

    Args:
        doc: Document to update
        xmp_data: Output from parse_xmp_sidecar

    Returns:
        Updated Document (mutates in place and returns same instance)
    """
    if not xmp_data:
        return doc

    if doc.metadata is None:
        doc.metadata = {}

    # Merge: XMP values fill in gaps, don't overwrite existing metadata
    for xmp_key, value in xmp_data.items():
        if xmp_key not in doc.metadata or not doc.metadata[xmp_key]:
            doc.metadata[xmp_key] = value

    # Mark that this document has XMP sidecar
    doc.metadata["_xmp_sidecar"] = True

    return doc


def has_xmp_sidecar(image_path: Path | str) -> bool:
    """Check if an XMP sidecar exists for the given image."""
    sidecar = xmp_sidecar_path(image_path)
    return sidecar is not None and sidecar.exists()


# Type hint only import
if TYPE_CHECKING:
    from fichero.models import Document
