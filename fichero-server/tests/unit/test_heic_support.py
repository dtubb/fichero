"""HEIC decodes, and the capability answers honestly (#4214).

HEIC is the iPhone camera default. Before pillow-heif was a declared
dependency, a `.heic` file routed correctly as an image and imported without
error, and then Pillow raised UnidentifiedImageError deep inside the render —
so the user got a record with no thumbnail, no picture, and no error. That is
the wrong-but-silent shape: it gets reported as "thumbnails are broken".

These tests go through the ENGINE's seam (`_load_pil` registers the opener),
not through `pillow_heif` directly — a test that imports the library itself
would pass while the engine still could not decode anything.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from tests.fixture_paths import sample_file

FIXTURE = (
    sample_file("sample.heic")
)


def test_the_fixture_is_really_heic():
    """Magic sits at offset 4 (`ftyp` box), so a renamed JPEG would not pass."""
    head = FIXTURE.read_bytes()[:24]

    assert b"ftyp" in head and (b"heic" in head or b"mif1" in head), head


class TestTheCapability:
    def test_heif_is_supported(self):
        from fichero_server.db.storage import heif_supported

        assert heif_supported() is True

    def test_loading_pil_registers_the_opener(self):
        """The registration must ride on the existing lazy PIL load, or the
        engine boot path silently never registers it."""
        from PIL import Image

        from fichero_server.db.storage import _load_pil

        _load_pil()

        assert "HEIF" in Image.OPEN

    def test_the_capability_reports_false_without_pillow_heif(self, monkeypatch):
        """Honest answer on a partial install — the point of having a seam.

        A missing pillow-heif must degrade to "HEIC unsupported", not take
        every other format's thumbnail down with it.
        """
        import builtins

        from fichero_server.db import storage

        real_import = builtins.__import__

        def no_pillow_heif(name, *args, **kwargs):
            if name == "pillow_heif":
                raise ImportError("simulated missing pillow-heif")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", no_pillow_heif)

        assert storage._register_heif() is False


class TestItActuallyRenders:
    def test_a_heic_document_gets_a_thumbnail(self, db, test_package, tmp_path):
        """End to end: the failure users saw was a missing thumbnail."""
        import shutil

        from fichero_server.db.storage import ensure_thumbnail
        from fichero_server.importers.ingest import IngestMode, ingest_file

        source = tmp_path / "IMG_2001.heic"
        shutil.copy(FIXTURE, source)
        doc = ingest_file(
            source,
            mode=IngestMode.LINK,
            db=db,
            package_path=Path(test_package),
            extract_text=False,
            auto_embed=False,
        )

        thumb = ensure_thumbnail(doc, package_path=Path(test_package), db=db)

        assert thumb is not None, "HEIC import produced no thumbnail"
        assert thumb.exists() and thumb.stat().st_size > 0

    def test_a_corrupt_heic_fails_without_taking_down_the_renderer(
        self, db, test_package, tmp_path
    ):
        """Truncated bytes must return None, not raise out of ensure_thumbnail."""
        from fichero_server.db.storage import ensure_thumbnail
        from fichero_server.importers.ingest import IngestMode, ingest_file

        source = tmp_path / "broken.heic"
        source.write_bytes(FIXTURE.read_bytes()[:32])
        doc = ingest_file(
            source,
            mode=IngestMode.LINK,
            db=db,
            package_path=Path(test_package),
            extract_text=False,
            auto_embed=False,
        )

        assert ensure_thumbnail(doc, package_path=Path(test_package), db=db) is None


def test_pillow_heif_is_a_declared_dependency():
    """Installed-but-undeclared is how a dependency vanishes at bundle time."""
    pyproject = (
        Path(__file__).resolve().parents[2] / "pyproject.toml"
    ).read_text()

    # Both lists: [project].dependencies AND the Briefcase engine requires,
    # which is what actually gets bundled into the app.
    assert pyproject.count("pillow-heif") >= 2, pyproject.count("pillow-heif")


@pytest.mark.parametrize("suffix", [".heic", ".HEIC"])
def test_heic_routes_to_image_either_case(suffix, tmp_path):
    import shutil

    from fichero_server.importers.ingest import detect_file_type
    from fichero_server.models import FileType

    target = tmp_path / f"photo{suffix}"
    shutil.copy(FIXTURE, target)

    assert detect_file_type(target) == FileType.image
