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
