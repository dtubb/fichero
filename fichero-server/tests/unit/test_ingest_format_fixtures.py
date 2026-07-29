"""Real fixtures for the formats named but nothing exercised (#4206).

The audit found five formats routed by `detect_file_type` with a plausible
loader behind them and ZERO fixtures: rtf, .doc, .xls/.xlsx, heic, jp2. Routing
is not support — a format nobody can demonstrate working is a claim, not a
fact. These convert the claims into facts, and two of them turned out to be
gaps.

Every fixture is a GENUINE file of its format, not a renamed text file:
    sample.rtf   Rich Text Format data, version 1      (textutil)
    sample.doc   Composite Document File V2 (OLE2)     (textutil)
    sample.xlsx  Microsoft Excel 2007+ (OOXML zip)     (hand-built)
    sample.heic  ISO Media, HEIF Image HEVC            (sips)
    sample.jp2   JPEG 2000 Part 1                      (Pillow)

A renamed .txt would pass a routing assertion and prove nothing, which is the
failure mode these exist to avoid.

Spreadsheets are tested through the GENERIC file-import path, not
`POST /api/ingest/xlsx` — that endpoint creates one document per ROW and is
unreachable pending a product decision (#4210).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fichero_server.importers.ingest import _TEXT_EXTRACTABLE, FileType, detect_file_type
from tests.fixture_paths import SAMPLE_FILES_DIR

FIXTURES = SAMPLE_FILES_DIR


def _fixture(name: str) -> Path:
    path = FIXTURES / name
    assert path.is_file(), f"missing fixture {name}"
    return path


class TestFixturesAreGenuineFiles:
    """Guard the fixtures themselves: a renamed .txt would pass everything else."""

    @pytest.mark.parametrize(
        ("name", "magic"),
        [
            ("sample.rtf", b"{\\rtf"),
            ("sample.doc", b"\xd0\xcf\x11\xe0"),  # OLE2 compound document
            ("sample.xlsx", b"PK\x03\x04"),  # OOXML is a zip
            ("sample.jp2", b"\x00\x00\x00\x0cjP"),  # JP2 signature box
        ],
    )
    def test_file_starts_with_its_format_magic(self, name, magic):
        assert _fixture(name).read_bytes().startswith(magic), f"{name} is not really {name}"

    def test_heic_is_really_heic(self):
        """HEIC's magic sits at offset 4 (`ftyp` box), not offset 0."""
        head = _fixture("sample.heic").read_bytes()[:24]

        assert b"ftyp" in head and (b"heic" in head or b"mif1" in head), head[:24]


class TestRouting:
    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("sample.rtf", FileType.text),
            ("sample.doc", FileType.word),
            ("sample.xlsx", FileType.spreadsheet),
            ("sample.heic", FileType.image),
            ("sample.jp2", FileType.image),
        ],
    )
    def test_extension_routes_to_the_expected_type(self, name, expected):
        assert detect_file_type(_fixture(name)) == expected


class TestTextExtractionThatWorks:
    """VERIFIED support — text really comes out of these."""

    @pytest.mark.parametrize(
        ("name", "expected_fragment"),
        [
            ("sample.rtf", "Asprilla"),
            ("sample.xlsx", "Asprilla"),
        ],
    )
    def test_text_is_extracted(self, name, expected_fragment):
        from kreuzberg import extract_file_sync

        result = extract_file_sync(str(_fixture(name)))
        content = (getattr(result, "content", "") or "").strip()

        assert expected_fragment in content, f"{name} extracted: {content[:120]!r}"

    def test_rtf_yields_plain_body_text_not_markup(self):
        """`.rtf` routes to FileType.text; the loader must strip RTF control words."""
        from kreuzberg import extract_file_sync

        content = extract_file_sync(str(_fixture("sample.rtf"))).content

        assert "\\rtf" not in content and "petitioned the court" in content


class TestFormerGaps:
    """Both recorded gaps are now closed, and these are real assertions.

    They were `xfail(strict=True)` — passing BECAUSE the support was missing,
    and designed to fail the moment it landed, which is exactly what happened:
    HEIC in #4214 (pillow-heif) and legacy .doc in #4215 (textutil fallback).
    A gap recorded as a passing xfail cannot rot silently, and these two did
    not. The HEIC case moved down to TestImagesThatWork.

    Still unverified, stated as a claim rather than a fact: `.xls` (legacy
    BIFF) — no BIFF writer exists in the venv and hand-crafting one was not
    proportionate (#4206).
    """

    def test_legacy_doc_text_extraction(self):
        """Was a strict xfail until #4215 added the textutil fallback.

        kreuzberg still rejects this file ("Malformed MiniFAT"), so the
        assertion goes through the ENGINE's loader — which is the contract
        that matters — rather than through kreuzberg directly. See
        test_legacy_doc_extraction.py for the fallback's own tests.
        """
        import asyncio

        from fichero_server.loaders.document_loader import DocumentLoader

        content = asyncio.run(DocumentLoader().load(_fixture("sample.doc")))

        assert "Asprilla" in (content.text or "")


class TestImagesThatWork:
    def test_heic_can_be_decoded(self):
        """Was a strict xfail until #4214 added pillow-heif as a dependency.

        HEIC is the iPhone camera default; before the dependency landed, such
        a photo imported as a record with no thumbnail and no error. The
        decode goes through the engine's own capability seam, because it is
        `_load_pil()` that registers the HEIF opener — a passing test that
        imported pillow_heif itself would prove nothing about the engine.
        """
        from PIL import Image

        from fichero_server.db.storage import heif_supported

        assert heif_supported(), "pillow-heif is a declared dependency (#4214)"

        image = Image.open(_fixture("sample.heic"))
        image.load()

        assert image.size == (64, 64)

    def test_jp2_decodes(self):
        """JPEG 2000 is present in the archive corpus, so this one matters."""
        from PIL import Image

        image = Image.open(_fixture("sample.jp2"))
        image.load()

        assert image.size == (64, 64)

    @pytest.mark.parametrize("name", ["sample.heic", "sample.jp2"])
    def test_images_are_not_expected_to_extract_text(self, name):
        """Images carry no text at ingest; OCR is a later workflow, not a gap."""
        assert detect_file_type(_fixture(name)) not in _TEXT_EXTRACTABLE
