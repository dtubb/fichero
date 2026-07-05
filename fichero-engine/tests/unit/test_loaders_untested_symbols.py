"""Backend coverage for previously untested symbols in `fichero/loaders`."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
import inspect
import sys

import pytest
from PIL import Image
from unittest.mock import patch

from fichero.loaders.base import MediaContent, MediaLoader
from fichero.loaders.docling_loader import (
    DOCLING_FORMATS,
    DoclingLoader,
    load_with_docling_sync,
)
from fichero.loaders.document_loader import DocumentLoader
from fichero.loaders.iiif_loader import IIIFLoader, _get_safe
from fichero.loaders.image_loader import ImageLoader, UnsafeImageError
from fichero.loaders.pdf_loader import PDFLoader, PDFTextLoader
from fichero.loaders.unified import UnifiedLoader
from fichero.loaders.xmp_loader import (
    _parse_xmp_file,
    apply_xmp_to_document,
    has_xmp_sidecar,
    parse_xmp_sidecar,
    xmp_sidecar_path,
)


class DummyLoader(MediaLoader):
    def __init__(self, content: MediaContent):
        self._content = content

    async def load(self, _source):
        return self._content

    def can_handle(self, _source):
        return True


def test_media_content_text_and_image_flags():
    empty = MediaContent(source="x")
    assert empty.has_text is False
    assert empty.has_images is False

    text = MediaContent(source="x", text="  ")
    assert text.has_text is False
    assert text.page_count == 0

    with_images = MediaContent(source="x", images=[1, 2])
    assert with_images.has_images is True


def test_media_loader_base_is_abstract():
    assert inspect.isabstract(MediaLoader)
    with pytest.raises(TypeError):
        MediaLoader()  # pragma: no cover - abstract class guard


def test_media_loader_load_sync_without_running_loop():
    content = MediaContent(source="x", text="hello")
    loader = DummyLoader(content)
    assert loader.load_sync("x").text == "hello"


@pytest.mark.asyncio
async def test_media_loader_load_sync_with_running_loop():
    content = MediaContent(source="x", text="world")
    loader = DummyLoader(content)

    loop = asyncio.get_running_loop()
    assert loop.is_running()
    assert loader.load_sync("x").text == "world"


def test_docling_loader_can_handle_formats():
    loader = DoclingLoader()
    assert loader.can_handle(Path("document.pdf")) is True
    assert loader.can_handle(Path("/tmp/manifest.doc")) is True
    assert loader.can_handle(Path("image.png")) is False
    assert loader.can_handle("https://example.org/doc.pdf") is False


def test_docling_loader_supported_formats_property():
    loader = DoclingLoader()
    assert loader.supported_formats == DOCLING_FORMATS


def test_load_with_docling_sync_parses_text_and_metadata(tmp_path, monkeypatch):
    test_pdf = tmp_path / "document.pdf"
    test_pdf.write_bytes(b"%PDF-1.4")

    class _FakeDoc:
        title = "My doc"
        pages = [1, 2, 3]
        authors = ["Alice", "Bob"]

        def export_to_markdown(self):
            return "Hello *from* docling"

        def export_to_json(self):
            return '{"text":"json"}'

    class _FakeConverter:
        def convert(self, _path):
            return SimpleNamespace(document=_FakeDoc())

    monkeypatch.setattr(DoclingLoader, "_get_converter", lambda _self: _FakeConverter())

    content = load_with_docling_sync(test_pdf, extract_tables=False, output_format="markdown")

    assert content.source == str(test_pdf)
    assert "Hello *from* docling" in content.text
    assert content.metadata["source"] == str(test_pdf)
    assert content.metadata["num_pages"] == 3
    assert content.mime_type == "application/pdf"
    assert content.needs_vlm is False


def test_load_with_docling_sync_rethrows_converter_errors(tmp_path, monkeypatch):
    test_pdf = tmp_path / "document.pdf"
    test_pdf.write_bytes(b"%PDF-1.4")

    def _raise():
        raise RuntimeError("install docling")

    monkeypatch.setattr(DoclingLoader, "_get_converter", lambda _self: _raise())
    with pytest.raises(RuntimeError, match="install docling"):
        load_with_docling_sync(test_pdf)


def test_document_loader_can_handle_formats():
    loader = DocumentLoader()
    assert loader.can_handle(Path("paper.docx")) is True
    assert loader.can_handle(Path("notes.txt")) is True
    assert loader.can_handle(Path("photo.jpg")) is False


@pytest.mark.asyncio
async def test_document_loader_load_text_file_decodes_fallback_encoding(tmp_path):
    path = tmp_path / "latin1.txt"
    path.write_bytes("café".encode("latin-1"))

    loader = DocumentLoader()
    content = await loader.load(path)
    assert content.text == "café"
    assert content.metadata["original_format"] == "txt"
    assert content.needs_vlm is False


def test_document_loader_kreuzberg_missing_dependency_is_reported(tmp_path, monkeypatch):
    path = tmp_path / "paper.docx"
    path.write_bytes(b"")
    loader = DocumentLoader()

    monkeypatch.setitem(sys.modules, "kreuzberg", None)
    with pytest.raises(RuntimeError):
        asyncio.run(loader._load_with_kreuzberg(path))


def test_iiif_loader_can_handle_patterns():
    loader = IIIFLoader()
    assert loader.can_handle("https://example.org/iiif/manifest") is True
    assert loader.can_handle("https://example.org/manifest") is True
    assert loader.can_handle("https://example.org/notes.txt") is False
    assert loader.can_handle("notes.txt") is False


def test_iiif_loader_version_and_canvas_parsing():
    loader = IIIFLoader()
    assert loader._detect_version({"@context": "http://iiif.io/api/presentation/3/context.json"}) == "3.0"
    assert loader._detect_version({"items": []}) == "3.0"
    assert loader._detect_version({"sequences": []}) == "2.x"

    v3 = loader._get_canvases({"items": [{"id": "c1"}, {"id": "c2"}]})
    v2 = loader._get_canvases({"sequences": [{"canvases": [{"id": "c3"}]}]})
    image_url_payload = {
        "items": [{
            "items": [{
                "items": [{
                    "body": {"service": [{"@id": "https://images.example.com/id"}]}
                }]
            }]
        }]
    }

    assert len(v3) == 2
    assert len(v2) == 1
    assert loader._get_image_url(image_url_payload["items"][0]) == (
        "https://images.example.com/id/full/!1500,1500/0/default.jpg"
    )


def test_iiif_loader_image_url_and_label_helpers():
    loader = IIIFLoader(max_dimension=640)
    assert loader._build_image_url("https://images.example.com/abc/") == (
        "https://images.example.com/abc/full/!640,640/0/default.jpg"
    )
    assert loader._get_label({"label": "Catalog", "@none": "alt"}) == "Catalog"
    assert loader._get_label({"label": {"en": ["English"]}}) == "English"


class _IIIFResponse:
    def __init__(self, *, status: int, url: str, location: str | None = None):
        self.status = status
        self.url = url
        self.headers = {"location": location} if location else {}
        self.released = False

    def release(self):
        self.released = True


class _IIIFSession:
    def __init__(self, redirects: dict[str, str]):
        self.redirects = redirects
        self.requested: list[str] = []

    async def get(self, url: str, **kwargs):
        self.requested.append(str(url))
        assert kwargs.get("allow_redirects") is False
        location = self.redirects.get(str(url))
        if location:
            return _IIIFResponse(status=302, url=str(url), location=location)
        return _IIIFResponse(status=200, url=str(url))


@pytest.mark.asyncio
async def test_iiif_manifest_redirect_to_loopback_is_blocked():
    session = _IIIFSession({"https://example.org/iiif/manifest": "http://127.0.0.1:8765/"})

    with pytest.raises(ValueError, match="IIIF URL not allowed"):
        await _get_safe(session, "https://example.org/iiif/manifest")

    assert "http://127.0.0.1:8765/" not in session.requested


@pytest.mark.asyncio
async def test_iiif_embedded_image_metadata_url_is_blocked():
    session = _IIIFSession({"https://example.org/iiif/image": "http://169.254.169.254/"})

    with pytest.raises(ValueError, match="IIIF URL not allowed"):
        await _get_safe(session, "https://example.org/iiif/image")

    assert "http://169.254.169.254/" not in session.requested


def test_image_loader_can_handle_and_load_pil_image(tmp_path):
    image_path = tmp_path / "sample.png"
    Image.new("RGB", size=(4, 3), color=(255, 0, 0)).save(image_path)

    loader = ImageLoader()
    assert loader.can_handle(image_path) is True
    assert loader._get_mime_type(".png") == "image/png"

    loaded = asyncio.run(loader.load(image_path))
    assert loaded.source == str(image_path)
    assert len(loaded.images) == 1


def test_image_loader_load_raises_for_unknown_suffix(tmp_path):
    unknown = tmp_path / "sample.xyz"
    unknown.write_bytes(b"")
    loader = ImageLoader()
    assert loader.can_handle(unknown) is False
    with pytest.raises(ValueError, match="Unsupported image format"):
        asyncio.run(loader.load(unknown))


def test_image_loader_rejects_oversized_image(tmp_path, monkeypatch):
    image_path = tmp_path / "oversized.png"
    Image.new("RGB", size=(3, 3), color=(255, 0, 0)).save(image_path)

    monkeypatch.setattr("fichero.loaders.image_loader._MAX_IMAGE_PIXELS", 4)

    with pytest.raises(UnsafeImageError, match="Image too large for ingest"):
        asyncio.run(ImageLoader().load(image_path))


def test_pdf_loader_can_handle_and_is_a_pdf_loader():
    assert PDFLoader().can_handle(Path("file.pdf")) is True
    assert PDFLoader().can_handle(Path("file.docx")) is False


def test_pdf_text_loader_can_handle_pdf_files():
    assert PDFTextLoader().can_handle(Path("file.pdf")) is True


def test_unified_loader_supports_hint_lookup_and_can_handle():
    loader = UnifiedLoader()
    assert loader.can_handle(Path("file.pdf")) is True
    assert loader.can_handle(Path("notes.txt")) is True
    assert loader.can_handle("https://example.org/iiif/manifest") is True
    assert loader.can_handle(Path("notes.unknown")) is False

    assert loader._get_loader_by_hint("image") is not None
    assert loader._get_loader_by_hint("pdf") is not None
    assert loader._get_loader_by_hint("document") is not None
    assert loader._get_loader_by_hint("iiif") is not None
    assert loader._get_loader_by_hint("missing") is None


@pytest.mark.asyncio
async def test_unified_loader_load_sync_uses_image_hint(monkeypatch, tmp_path):
    async def _fake_load(self, source):
        return MediaContent(source=str(source), text="hinted")

    class HintImageLoader(ImageLoader):
        def can_handle(self, _source):
            return False

        async def load(self, source):
            return await _fake_load(self, source)

    monkeypatch.setattr("fichero.loaders.unified.ImageLoader", HintImageLoader)
    loader = UnifiedLoader()
    got = loader.load_sync(tmp_path / "file.jpg", hint="image")
    assert got.text == "hinted"


def test_xmp_sidecar_path_and_presence(tmp_path):
    image = tmp_path / "scan.TIFF"
    assert xmp_sidecar_path(image) == tmp_path / "scan.xmp"
    assert has_xmp_sidecar(image) is False

    sidecar = tmp_path / "scan.xmp"
    sidecar.write_text("<xmp></xmp>")
    assert has_xmp_sidecar(image) is True


def test_parse_xmp_sidecar_missing_file_returns_none(tmp_path):
    assert parse_xmp_sidecar(tmp_path / "missing.jpg") is None


def test_parse_xmp_sidecar_calls_parser_for_present_file(tmp_path):
    image = tmp_path / "scan.jpg"
    image.write_bytes(b"")
    sidecar = tmp_path / "scan.xmp"
    sidecar.write_text("<xmp></xmp>", encoding="utf-8")

    with patch("fichero.loaders.xmp_loader._parse_xmp_file") as parse_fn:
        parse_fn.return_value = {"xmp_title": "Archive page"}
        parsed = parse_xmp_sidecar(image)

    assert parsed == {"xmp_title": "Archive page"}
    parse_fn.assert_called_once_with(sidecar)


def test_parse_xmp_file_rejects_billion_laughs_entities(tmp_path):
    sidecar = tmp_path / "scan.xmp"
    sidecar.write_text(
        """<?xml version="1.0"?>
<!DOCTYPE lolz [
 <!ENTITY lol "lol">
 <!ENTITY lol1 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
]>
<x:xmpmeta>&lol1;</x:xmpmeta>
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="entity declarations"):
        _parse_xmp_file(sidecar)


def test_apply_xmp_to_document_merges_without_overwrite():
    doc = SimpleNamespace(metadata={"xmp_title": "Original", "other": "keep"})
    updated = apply_xmp_to_document(doc, {"xmp_title": "New", "xmp_issue": "123"})

    assert updated.metadata["xmp_title"] == "Original"
    assert updated.metadata["xmp_issue"] == "123"
    assert updated.metadata["other"] == "keep"
    assert updated.metadata["_xmp_sidecar"] is True
