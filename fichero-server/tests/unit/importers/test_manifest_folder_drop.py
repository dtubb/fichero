"""Dropping a folder that carries ``manifest.jsonl`` imports the corpus.

The UX path (Daniel 2026-08-17: "is there a way in UX to do it. if not,
that's priority"): the app's ordinary folder drop reaches
``import_folder_impl``, which detects the manifest and runs the SAME
importer as ``fichero import-manifest`` — transcripts into page_content,
entities, parenting under the drop target — instead of plain file ingest.
"""
from __future__ import annotations

from pathlib import Path

from fichero_server.api.routes.ingest.core import (
    IngestFolderRequest,
    _import_manifest_folder,
    import_folder_impl,
)
from fichero_server.models import Document

from .test_manifest_import import _fixture_manifest, _TestClientAdapter


def test_folder_with_manifest_routes_through_manifest_importer(client, db, test_package, tmp_path):
    manifest = _fixture_manifest(tmp_path)  # writes tmp_path/manifest.jsonl
    request = IngestFolderRequest(path=str(tmp_path))
    progress: list[tuple[int, int]] = []

    docs = _import_manifest_folder(
        db,
        manifest,
        request,
        Path(test_package),
        on_progress=lambda cur, total: progress.append((cur, total)),
        # Production builds the in-process self-client; tests speak through
        # the same TestClient adapter the manifest suite uses.
        manifest_client=_TestClientAdapter(client),
    )

    names = {d.name for d in docs}
    assert "Tiny Corpus" in names and "page_001" in names
    # ENGINE-RECORDED path stamp (2026-08-17: pathless linked pages meant no
    # thumbnails): the drop path writes the preferred rendition's source onto
    # the document when the ingest authority allows it (pytest tmp is an
    # allowed ingest root, mirroring a real drop's grant).
    page = next(d for d in docs if d.name == "page_001")
    assert page.path and page.path.endswith("page_001_enhanced.jpg")
    # Real Document rows, not summaries — the caller queues derivatives on these.
    assert all(isinstance(d, Document) for d in docs)
    # The page's transcript landed as page_content via the live routes.
    page = next(d for d in docs if d.name == "page_001")
    assert page.page_content
    assert progress and progress[-1][0] == progress[-1][1] == len(docs)


def test_drop_target_becomes_corpus_root_parent(client, db, test_package, tmp_path):
    target = client.post(
        "/api/documents", json={"name": "Drop Target", "doc_type": "folder"}
    ).json()
    manifest = _fixture_manifest(tmp_path)
    request = IngestFolderRequest(path=str(tmp_path), parent_id=target["id"])

    docs = _import_manifest_folder(
        db,
        manifest,
        request,
        Path(test_package),
        manifest_client=_TestClientAdapter(client),
    )

    root = next(d for d in docs if d.name == "Tiny Corpus")
    assert root.parent_id == target["id"], (
        "the corpus root must land under the folder the user dropped onto, "
        "not at library root"
    )


def test_plain_folder_without_manifest_uses_normal_ingest(db, test_package, tmp_path):
    folder = tmp_path / "plain"
    folder.mkdir()
    (folder / "note.txt").write_text("just a text file")

    docs = import_folder_impl(db, IngestFolderRequest(path=str(folder)), Path(test_package))

    assert [d.name for d in docs] == ["note.txt"], (
        "no manifest → the pre-existing plain ingest path, byte-for-byte"
    )


def test_in_process_client_passes_the_loopback_guard(client, db, test_package, monkeypatch):
    """Reproduces the first live drop (2026-08-17): GET /documents -> 403
    "loopback only". TestClient's synthetic host is trusted only under
    pytest, so production must ride the sanctioned in-memory transport
    stamp. Deleting PYTEST_CURRENT_TEST makes this test see what the live
    app saw — it passes ONLY through the stamp."""
    from fichero_server.api.routes.ingest.core import _InProcessManifestClient

    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    in_process = _InProcessManifestClient(str(test_package))
    result = in_process.request("GET", "/documents?limit=1")
    assert result is not None, "the stamped in-memory transport must clear the loopback guard"


def test_drop_stamps_engine_recorded_source_paths(client, db, test_package, tmp_path, monkeypatch):
    """With the source under the ingest authority (as a real drop's grant
    provides), the drop path stamps the preferred rendition's path onto the
    document — engine-recorded, which is what thumbnails and serving trust."""
    import fichero_server.api.routes.ingest.core as core

    manifest = _fixture_manifest(tmp_path)
    monkeypatch.setattr(core, "is_allowed_ingest_path", lambda p: True, raising=False)
    # The stamp imports the authority inside the function; patch its source.
    import fichero_server.security.path_security as ps

    monkeypatch.setattr(ps, "is_allowed_ingest_path", lambda p: True)

    docs = _import_manifest_folder(
        db,
        manifest,
        IngestFolderRequest(path=str(tmp_path)),
        Path(test_package),
        manifest_client=_TestClientAdapter(client),
    )
    page = next(d for d in docs if d.name == "page_001")
    assert page.path and page.path.endswith("page_001_enhanced.jpg")
    persisted = db.get(type(page), page.id)
    assert persisted.path == page.path, "the stamp is engine-RECORDED, not in-memory"


def test_drop_declines_paths_outside_the_ingest_authority(client, db, test_package, tmp_path, monkeypatch):
    """A source the ingest authority refuses stays pathless — recorded in
    metadata only, never a guessed grant."""
    import fichero_server.security.path_security as ps

    manifest = _fixture_manifest(tmp_path)
    monkeypatch.setattr(ps, "is_allowed_ingest_path", lambda p: False)

    docs = _import_manifest_folder(
        db,
        manifest,
        IngestFolderRequest(path=str(tmp_path)),
        Path(test_package),
        manifest_client=_TestClientAdapter(client),
    )
    page = next(d for d in docs if d.name == "page_001")
    assert page.path is None


def test_redrop_repairs_a_pathless_earlier_import(client, db, test_package, tmp_path):
    """2026-08-17 live: a failed delete + idempotent skip made the second
    drop a silent no-op — same pathless pages, still no thumbnails. A
    re-drop must return the SEEN documents and stamp the pathless ones."""
    manifest = _fixture_manifest(tmp_path)
    request = IngestFolderRequest(path=str(tmp_path))

    first = _import_manifest_folder(
        db, manifest, request, Path(test_package),
        manifest_client=_TestClientAdapter(client),
    )
    page = next(d for d in first if d.name == "page_001")
    # Simulate the pre-fix import: strip the stamp.
    page.path = None
    db.save(page)

    second = _import_manifest_folder(
        db, manifest, request, Path(test_package),
        manifest_client=_TestClientAdapter(client),
    )
    assert second, "a re-drop reports the corpus it touched, not an empty no-op"
    repaired = next(d for d in second if d.name == "page_001")
    assert repaired.path and repaired.path.endswith("page_001_enhanced.jpg")


def test_manifest_imported_corpus_deletes_cleanly(client, db, test_package, tmp_path):
    """2026-08-17 live: right-click delete of the imported corpus errored.
    A manifest corpus carries shapes plain folders don't (transcript
    artifacts, entity links, claims) — deletion through the same route the
    sidebar uses must succeed and take the children with it."""
    manifest = _fixture_manifest(tmp_path)
    docs = _import_manifest_folder(
        db, manifest, IngestFolderRequest(path=str(tmp_path)), Path(test_package),
        manifest_client=_TestClientAdapter(client),
    )
    root = next(d for d in docs if d.name == "Tiny Corpus")

    resp = client.delete(f"/api/documents/{root.id}")
    assert resp.status_code < 400, f"delete failed: {resp.status_code} {resp.text[:300]}"

    listing = client.get("/api/documents?limit=500").json()
    items = listing["items"] if isinstance(listing, dict) else listing
    names = {d["name"] for d in items}
    assert "Tiny Corpus" not in names
    assert "page_001" not in names, "children must go with the corpus"
