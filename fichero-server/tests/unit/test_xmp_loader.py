"""Coverage for the XMP sidecar loader ``fichero_server.loaders.xmp_loader``
(effectively untested — only an auto-generated import smoke). Pure logic:
sidecar path derivation, the regex-based XMP field parser (attribute / element /
array forms), the XXE-rejection path, and the non-overwriting metadata merge.

Exact field assertions target ``_parse_xmp_regex`` directly (deterministic
regardless of whether libxmp is installed); integration cases go through
``parse_xmp_sidecar``.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from fichero_server.loaders.xmp_loader import (
    _parse_xmp_regex,
    apply_xmp_to_document,
    has_xmp_sidecar,
    parse_xmp_sidecar,
    xmp_sidecar_path,
)

XMP_DOC = """<?xml version="1.0"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description
     xmlns:dc="http://purl.org/dc/elements/1.1/"
     xmlns:ficher="https://fichero.app/xmp/1.0/"
     ficher:archiveId="AGN-123">
   <dc:title><rdf:Alt><rdf:li xml:lang="x-default">A Photo</rdf:li></rdf:Alt></dc:title>
   <dc:subject><rdf:Bag><rdf:li>gold</rdf:li><rdf:li>mining</rdf:li></rdf:Bag></dc:subject>
   <dc:description>A scan of a deed</dc:description>
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>"""


def _write(tmp_path, name, text) -> Path:
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


# ===========================================================================
# xmp_sidecar_path / has_xmp_sidecar
# ===========================================================================


def test_sidecar_path_swaps_extension():
    assert xmp_sidecar_path("/photos/image.jpg") == Path("/photos/image.xmp")
    # Case in the original extension doesn't matter — stem + .xmp.
    assert xmp_sidecar_path("/archive/scan.TIFF") == Path("/archive/scan.xmp")
    assert xmp_sidecar_path("photo.jpeg") == Path("photo.xmp")


def test_sidecar_path_none_when_no_filename():
    assert xmp_sidecar_path("/") is None


def test_has_xmp_sidecar(tmp_path):
    img = tmp_path / "pic.jpg"
    img.write_text("img")
    assert has_xmp_sidecar(img) is False
    (tmp_path / "pic.xmp").write_text(XMP_DOC)
    assert has_xmp_sidecar(img) is True


# ===========================================================================
# _parse_xmp_regex — the three serialization forms
# ===========================================================================


def test_regex_parses_attribute_element_and_array_forms(tmp_path):
    result = _parse_xmp_regex(_write(tmp_path, "x.xmp", XMP_DOC))
    assert result["xmp_archive_id"] == "AGN-123"          # attribute form
    assert result["xmp_description"] == "A scan of a deed"  # element form
    assert result["xmp_title"] == "A Photo"                # rdf:Alt -> li
    assert result["xmp_keywords"] == "gold, mining"        # rdf:Bag -> joined


def test_regex_ignores_unknown_namespace(tmp_path):
    doc = (
        '<rdf:Description xmlns:foo="http://example.com/foo/" foo:title="X" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" dc:rights="Public Domain"/>'
    )
    result = _parse_xmp_regex(_write(tmp_path, "x.xmp", doc))
    assert result == {"xmp_rights": "Public Domain"}  # foo: not in the map


def test_regex_empty_document_yields_empty_dict(tmp_path):
    assert _parse_xmp_regex(_write(tmp_path, "x.xmp", "<rdf:RDF></rdf:RDF>")) == {}


def test_regex_prefix_field_not_confused_by_longer_name(tmp_path):
    # 'photoshop:City' must not be matched inside 'photoshop:CityCode'.
    doc = (
        '<rdf:Description xmlns:photoshop="http://ns.adobe.com/photoshop/1.0/" '
        'photoshop:CityCode="ZZ"/>'
    )
    result = _parse_xmp_regex(_write(tmp_path, "x.xmp", doc))
    assert "xmp_city" not in result


# ===========================================================================
# parse_xmp_sidecar — integration + security
# ===========================================================================


def test_parse_sidecar_returns_none_without_file(tmp_path):
    assert parse_xmp_sidecar(tmp_path / "missing.jpg") is None


def test_parse_sidecar_reads_sibling(tmp_path):
    img = tmp_path / "pic.jpg"
    img.write_text("img")
    _write(tmp_path, "pic.xmp", XMP_DOC)
    result = parse_xmp_sidecar(img)
    assert result is not None
    assert result.get("xmp_title") == "A Photo"


def test_parse_sidecar_rejects_xxe_entities(tmp_path):
    # XXE / external-entity XMP must be rejected (reject_xml_entities) and the
    # loader degrades to None rather than resolving the entity.
    xxe = (
        '<?xml version="1.0"?>'
        '<!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>'
        '<rdf:RDF><rdf:Description dc:title="&xxe;"/></rdf:RDF>'
    )
    img = tmp_path / "evil.jpg"
    img.write_text("img")
    _write(tmp_path, "evil.xmp", xxe)
    assert parse_xmp_sidecar(img) is None


# ===========================================================================
# apply_xmp_to_document — non-overwriting merge
# ===========================================================================


def test_apply_fills_empty_metadata_and_marks_sidecar():
    doc = SimpleNamespace(metadata=None)
    out = apply_xmp_to_document(doc, {"xmp_title": "T"})
    assert out is doc
    assert doc.metadata["xmp_title"] == "T"
    assert doc.metadata["_xmp_sidecar"] is True


def test_apply_does_not_overwrite_existing_values():
    doc = SimpleNamespace(metadata={"xmp_title": "Curated", "xmp_city": ""})
    apply_xmp_to_document(doc, {"xmp_title": "FromXMP", "xmp_city": "Bogotá"})
    assert doc.metadata["xmp_title"] == "Curated"  # existing non-empty wins
    assert doc.metadata["xmp_city"] == "Bogotá"    # empty existing gets filled


def test_apply_empty_xmp_data_is_noop():
    doc = SimpleNamespace(metadata={"a": 1})
    apply_xmp_to_document(doc, {})
    # Early return -> no _xmp_sidecar marker written.
    assert "_xmp_sidecar" not in doc.metadata
    assert doc.metadata == {"a": 1}
