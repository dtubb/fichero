"""Link mode from the CLI gives pages that reference their image in place (#5383).

WHY: the routes contract (#4230) refuses a client-supplied absolute path, and only the app's drop
path stamps engine-recorded paths afterwards. From the CLI nothing stamped, so the default link
mode made 49 pathless pages for the Sergio notebooks while reporting success: no image, no workflow
could run. The CLI now links through the engine's own ingest with copying off, so the engine records
and checks each path itself and no bytes are copied. The drop path is unchanged.
"""
from __future__ import annotations

from pathlib import Path

from fichero_server.importers.manifest_import import import_manifest
from fichero_server.models import Document

from .test_manifest_import import _fixture_manifest, _TestClientAdapter


def test_cli_link_gives_every_page_its_image_without_copying(client, db, test_package, tmp_path, monkeypatch):
    import fichero_server.security.path_security as ps

    monkeypatch.setattr(ps, "is_allowed_ingest_path", lambda p: True)  # the engine may read tmp_path
    manifest = _fixture_manifest(tmp_path)
    from PIL import Image

    Image.new("RGB", (40, 30), "white").save(tmp_path / "page_001_enhanced.jpg")  # a real photo
    summary = import_manifest(_TestClientAdapter(client), manifest, str(test_package),
                              ingest_mode="link", link_in_place=True)

    pages = [db.get(Document, i) for i in summary.seen_document_ids]
    pages = [p for p in pages if p is not None and p.name.startswith("page_")]
    assert pages, "the fixture has pages"
    for page in pages:
        assert page.path, f"{page.name} was left without its image"
        assert Path(page.path).is_relative_to(tmp_path), "link must reference in place, not copy"
    assert not list((Path(test_package) / "files").rglob("*.jpg")), "link copied bytes into the library"
