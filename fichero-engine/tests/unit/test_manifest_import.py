"""Tests for the canonical manifest importer (`fichero import-manifest`).

The importer drives the real FastAPI routes (`POST /api/documents`,
`/api/entities`, `/api/claims`) through a transport-agnostic client. Here we
adapt the conftest `client` (a FastAPI ``TestClient`` bound to a temp library)
into the importer's ``ManifestApiClient`` interface, so the import runs
end-to-end against the actual routes + a real temp DB — no live server, no raw
``db.save``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fichero.importers.manifest_import import import_manifest, validate_nodes
from fichero.models import Document


CANONICAL_VERSION = "fichero-corpus-import-v1"


class _TestClientAdapter:
    """Adapt a FastAPI ``TestClient`` to the ``ManifestApiClient`` protocol."""

    def __init__(self, test_client) -> None:
        self._client = test_client

    def request(
        self, method: str, path: str, body: dict[str, Any] | None = None
    ) -> Any:
        url = f"/api{path}"
        if method == "GET":
            resp = self._client.get(url)
        elif method == "POST":
            resp = self._client.post(url, json=body)
        elif method == "PUT":
            resp = self._client.put(url, json=body)
        else:  # pragma: no cover - importer only uses GET/POST/PUT
            raise AssertionError(f"unexpected method {method}")
        # Preview-warm GETs (/storage/thumbnail|display/<id>) are best-effort:
        # a 404 (e.g. unrenderable test bytes) is not an importer failure —
        # mirror the real client's tolerance by returning None instead of
        # raising, so warnings stay empty for the happy-path assertions.
        if method == "GET" and path.startswith("/storage/") and resp.status_code >= 400:
            return None
        assert resp.status_code < 400, (method, url, resp.status_code, resp.text)
        if resp.content:
            try:
                return resp.json()
            except ValueError:
                return None
        return None


def _fixture_manifest(tmp_path: Path) -> Path:
    """Write a tiny 2-document manifest: a group + one page under it."""
    img_src = tmp_path / "page_001_enhanced.jpg"
    img_src.write_bytes(b"not-a-real-image")  # referenced, never copied

    nodes = [
        {
            "canonical_version": CANONICAL_VERSION,
            "node_type": "group",
            "external_id": "tiny_corpus",
            "parent_external_id": None,
            "corpus": "tiny_corpus",
            "name": "Tiny Corpus",
            "page_label": None,
            "date": "1923",
            "language": "en",
            "text": None,
            "images": [],
            "entities": [],
            "claims": [],
            "metadata": {"source_assets": str(tmp_path)},
        },
        {
            "canonical_version": CANONICAL_VERSION,
            "node_type": "page",
            "external_id": "tiny_corpus__page_001",
            "parent_external_id": "tiny_corpus",
            "corpus": "tiny_corpus",
            "name": "page_001",
            "sequence": 1,
            "page_label": "001",
            "date": "1923-02-05",
            "language": "en",
            "text": "Marshall went to Istmina this afternoon.",
            "images": [
                {
                    "role": "enhanced",
                    "path": "images/enhanced/page_001.jpg",
                    "source_path": str(img_src),
                    "is_representative": True,
                    "metadata": {},
                }
            ],
            "entities": [
                {
                    "external_id": "Marshall",
                    "canonical_name": "Marshall",
                    "entity_type": "person",
                    "aliases": [],
                    "language": "en",
                    "metadata": {"source": "test"},
                },
                {
                    "external_id": "Istmina",
                    "canonical_name": "Istmina",
                    "entity_type": "location",
                    "aliases": [],
                    "language": "en",
                    "metadata": {"source": "test"},
                },
            ],
            "claims": [
                {
                    "external_id": "tiny_corpus__page_001__claim_0",
                    "text": "Marshall went to Istmina",
                    "source_excerpt": "Marshall went to Istmina this afternoon.",
                    "source_ref": "tiny_corpus__page_001",
                    "entity_refs": ["Marshall", "Istmina"],
                    "claim_type": "fact",
                    "confidence": 0.4,
                    "language": "en",
                    "subject_canonical": "Marshall",
                    "predicate_verb": "went to",
                    "object_phrase": "Istmina this afternoon",
                    "claim_recorded_at": "1923-02-05",
                    "metadata": {"source": "test"},
                }
            ],
        },
    ]

    manifest = tmp_path / "manifest.jsonl"
    with manifest.open("w", encoding="utf-8") as handle:
        for node in nodes:
            handle.write(json.dumps(node) + "\n")
    return manifest


def test_validate_rejects_wrong_version():
    bad = [{"canonical_version": "other-v9", "external_id": "x", "node_type": "page"}]
    try:
        validate_nodes(bad)
    except ValueError as exc:
        assert "canonical_version" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError for wrong canonical_version")


def test_validate_rejects_out_of_order_parent():
    nodes = [
        {
            "canonical_version": CANONICAL_VERSION,
            "external_id": "child",
            "node_type": "page",
            "parent_external_id": "missing_parent",
        }
    ]
    try:
        validate_nodes(nodes)
    except ValueError as exc:
        assert "parent" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError for out-of-order parent")


def test_import_creates_documents_entities_claims(client, db, tmp_path):
    manifest = _fixture_manifest(tmp_path)
    adapter = _TestClientAdapter(client)

    summary = import_manifest(adapter, manifest, str(tmp_path / "lib.fichero"))

    # Counts from the run summary.
    assert summary.nodes_seen == 2
    assert summary.pages_seen == 1
    assert summary.documents_created == 2
    assert summary.entities_created == 2
    assert summary.artifacts_created == 4
    assert summary.claims_created == 1
    assert summary.warnings == []

    # Verify through the live routes that the data actually landed.
    docs = client.get("/api/documents?limit=500").json()
    items = docs["items"] if isinstance(docs, dict) else docs
    by_name = {d["name"]: d for d in items}
    assert "Tiny Corpus" in by_name
    assert "page_001" in by_name

    page = by_name["page_001"]
    # Parent wiring: page -> group.
    assert page["parent_id"] == by_name["Tiny Corpus"]["id"]
    # External absolute sources stay in metadata; they are not promoted into
    # the servable Document.path field.
    assert page["path"] is None
    # Renditions preserved in metadata.
    assert page["metadata"]["canonical_external_id"] == "tiny_corpus__page_001"
    assert page["metadata"]["images"][0]["role"] == "enhanced"

    entities = client.get("/api/entities?limit=500").json()
    ent_items = entities["items"] if isinstance(entities, dict) else entities
    names = {e["canonical_name"] for e in ent_items}
    assert {"Marshall", "Istmina"} <= names
    by_entity_name = {e["canonical_name"]: e for e in ent_items}
    assert page["id"] in by_entity_name["Marshall"]["source_document_ids"]
    assert page["id"] in by_entity_name["Istmina"]["source_document_ids"]

    page_artifacts = client.get(
        f"/api/artifacts/document/{page['id']}?include_descendants=false"
    ).json()
    artifact_types = {a["artifact_type"] for a in page_artifacts["items"]}
    assert {"import_receipt", "transcription", "people", "places"} <= artifact_types
    import_receipt = next(
        a for a in page_artifacts["items"] if a["artifact_type"] == "import_receipt"
    )
    assert import_receipt["data"]["external_id"] == "tiny_corpus__page_001"
    assert import_receipt["data"]["page_label"] == "001"
    transcription = next(
        a for a in page_artifacts["items"] if a["artifact_type"] == "transcription"
    )
    assert transcription["content"] == "Marshall went to Istmina this afternoon."
    people = next(a for a in page_artifacts["items"] if a["artifact_type"] == "people")
    assert people["data"]["items"][0]["name"] == "Marshall"
    places = next(a for a in page_artifacts["items"] if a["artifact_type"] == "places")
    assert places["data"]["items"][0]["name"] == "Istmina"

    claims = client.get("/api/claims?limit=500").json()
    claim_items = claims["items"] if isinstance(claims, dict) else claims
    assert len(claim_items) == 1
    claim = claim_items[0]
    assert claim["text"] == "Marshall went to Istmina"
    # Claim links to both entities (resolved from entity_refs -> ids).
    assert len(claim["entity_ids"]) == 2
    assert claim["source_document_id"] == page["id"]


class _RecordingClient:
    """Mock ``ManifestApiClient`` that records every request.

    Returns synthetic ids for POST /documents and POST /ingest/file so the
    importer can wire parents and continue. Used to assert copy-image
    behaviour without a live engine.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict | None]] = []
        self._counter = 0

    def request(self, method, path, body=None):
        self.calls.append((method, path, body))
        if method == "GET":
            # /storage/thumbnail|display/<id> preview-warm GETs return nothing.
            if path.startswith("/storage/"):
                return None
            return {"items": []}
        if method == "POST" and path == "/ingest/file":
            self._counter += 1
            # Real ingest returns the COPIED in-library path so the importer can
            # rewrite the active image path to local.
            return {
                "id": f"doc-{self._counter}",
                "path": f"files/co/copied_{self._counter}.jpg",
            }
        if method == "POST" and path == "/documents":
            self._counter += 1
            return {"id": f"doc-{self._counter}"}
        if method == "POST" and path in ("/entities", "/claims"):
            self._counter += 1
            return {"id": f"obj-{self._counter}"}
        if method == "PUT":
            return {"id": path.rsplit("/", 1)[-1]}
        return None


def test_copy_images_triggers_ingest_copy_and_keeps_page_content(tmp_path):
    """copy_images=True copies the image via the native ingest path AND still
    sets the manifest transcript as page_content (provenance import)."""
    from fichero.importers.manifest_import import import_manifest

    manifest = _fixture_manifest(tmp_path)
    rec = _RecordingClient()

    summary = import_manifest(
        rec, manifest, str(tmp_path / "lib.fichero"), copy_images=True
    )

    assert summary.documents_created == 2

    # The page image was copied INTO the library via the native ingest path
    # (copy_mode=True), NOT referenced via POST /documents.
    ingest_calls = [c for c in rec.calls if c[1] == "/ingest/file"]
    assert len(ingest_calls) == 1
    ingest_body = ingest_calls[0][2]
    assert ingest_body["copy_mode"] is True
    assert ingest_body["path"] == str(tmp_path / "page_001_enhanced.jpg")
    # No OCR / text-extraction on ingest — transcript comes from the manifest.
    assert ingest_body["extract_text"] is False

    # The page document is then updated with the clean manifest transcript and
    # provenance=import (NOT Apple Vision OCR).
    put_calls = [c for c in rec.calls if c[0] == "PUT"]
    assert len(put_calls) == 1
    put_body = put_calls[0][2]
    assert put_body["page_content"] == "Marshall went to Istmina this afternoon."
    assert put_body["metadata"]["provenance"] == "import"
    assert put_body["metadata"]["canonical_external_id"] == "tiny_corpus__page_001"
    assert put_body["metadata"]["ingest_mode"] == "copy"

    # Copy mode rewrites the active image path to the LOCAL in-library file so
    # the app never reaches over the network; the original is preserved.
    img = put_body["metadata"]["images"][0]
    assert img["source_path"].startswith("files/")
    assert img["original_source_path"] == str(tmp_path / "page_001_enhanced.jpg")

    # The group container (no image) still goes through the reference create
    # path — and is imported as a navigable FOLDER (not doc_type "group").
    doc_posts = [c for c in rec.calls if c[1] == "/documents"]
    assert len(doc_posts) == 1
    assert doc_posts[0][2]["name"] == "Tiny Corpus"
    assert doc_posts[0][2]["doc_type"] == "folder"

    # A local preview is warmed for the page (thumbnail + display).
    storage_gets = [c for c in rec.calls if c[0] == "GET" and c[1].startswith("/storage/")]
    assert any("/storage/thumbnail/" in c[1] for c in storage_gets)
    assert any("/storage/display/" in c[1] for c in storage_gets)


def test_link_mode_references_source_and_warms_local_preview(tmp_path):
    """Default (link) preserves source metadata without copying bytes and still
    warms a local preview cache."""
    from fichero.importers.manifest_import import import_manifest

    manifest = _fixture_manifest(tmp_path)
    rec = _RecordingClient()

    import_manifest(rec, manifest, str(tmp_path / "lib.fichero"))

    # No bytes copied, no PUT rewrite of the page.
    assert not [c for c in rec.calls if c[1] == "/ingest/file"]
    assert not [c for c in rec.calls if c[0] == "PUT"]
    page_post = next(
        c for c in rec.calls if c[1] == "/documents" and c[2]["name"] == "page_001"
    )
    # The external absolute source is metadata only; Document.path is reserved
    # for confined, servable paths.
    assert page_post[2]["path"] is None
    assert page_post[2]["metadata"]["images"][0]["source_path"] == str(
        tmp_path / "page_001_enhanced.jpg"
    )
    assert "original_source_path" not in page_post[2]["metadata"]["images"][0]
    assert page_post[2]["page_content"] == "Marshall went to Istmina this afternoon."

    # Even in link mode, a local thumbnail + display preview is warmed.
    storage_gets = [c for c in rec.calls if c[0] == "GET" and c[1].startswith("/storage/")]
    assert any("/storage/thumbnail/" in c[1] for c in storage_gets)
    assert any("/storage/display/" in c[1] for c in storage_gets)


def test_resolve_ingest_mode_and_legacy_alias():
    """ingest_mode wins; copy_images is the legacy alias for 'copy'."""
    from fichero.importers.manifest_import import resolve_ingest_mode

    assert resolve_ingest_mode(None, False) == "link"  # default
    assert resolve_ingest_mode(None, True) == "copy"  # legacy alias
    assert resolve_ingest_mode("link", False) == "link"
    assert resolve_ingest_mode("COPY", False) == "copy"  # case-insensitive
    assert resolve_ingest_mode("move", False) == "move"
    # Explicit ingest_mode overrides the legacy copy_images flag.
    assert resolve_ingest_mode("link", True) == "link"
    try:
        resolve_ingest_mode("teleport", False)
    except ValueError as exc:
        assert "Unknown ingest mode" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError for unknown ingest mode")


def test_group_node_maps_to_folder_doc_type():
    """A manifest 'group' container imports as a navigable FOLDER (not a leaf
    doc_type 'group') so its child pages render in the app grid."""
    from fichero.importers.manifest_import import _NODE_TYPE_TO_DOC_TYPE, document_payload

    assert _NODE_TYPE_TO_DOC_TYPE["group"] == "folder"
    node = {
        "canonical_version": CANONICAL_VERSION,
        "node_type": "group",
        "external_id": "container",
        "name": "Container",
        "images": [],
        "metadata": {},
    }
    payload = document_payload(node, parent_id="parent-1")
    assert payload["doc_type"] == "folder"


def test_move_refuses_to_delete_network_source(tmp_path, monkeypatch):
    """Move mode copies the bytes in, but a source on a network/removable
    volume (e.g. /Volumes/...) is NEVER deleted — fall back to copy-and-warn."""
    import fichero.importers.manifest_import as mi

    deleted: list[str] = []

    real_unlink = Path.unlink

    def _spy_unlink(self, *a, **k):  # pragma: no cover - should not be hit
        deleted.append(str(self))
        return real_unlink(self, *a, **k)

    monkeypatch.setattr(Path, "unlink", _spy_unlink)

    # Build a manifest whose page image source_path is on a /Volumes mount.
    network_src = "/Volumes/Files/corpus/page_001.jpg"
    nodes = [
        {
            "canonical_version": CANONICAL_VERSION,
            "node_type": "page",
            "external_id": "vol__page_001",
            "parent_external_id": None,
            "name": "page_001",
            "text": "remote page",
            "images": [
                {"role": "enhanced", "source_path": network_src, "metadata": {}}
            ],
            "entities": [],
            "claims": [],
            "metadata": {},
        }
    ]
    manifest = tmp_path / "vol.jsonl"
    with manifest.open("w", encoding="utf-8") as handle:
        for node in nodes:
            handle.write(json.dumps(node) + "\n")

    rec = _RecordingClient()
    summary = mi.import_manifest(
        rec, manifest, str(tmp_path / "lib.fichero"), ingest_mode="move"
    )

    # Bytes were copied in (ingest/file called), but the network source was
    # NOT deleted, and a warning records the refusal.
    assert [c for c in rec.calls if c[1] == "/ingest/file"]
    assert deleted == []
    assert any("refusing to delete" in w for w in summary.warnings)


def test_is_safe_to_delete_source_rules():
    """Local boot-volume paths under $HOME are safe; /Volumes and outside-home
    are not."""
    import os

    from fichero.importers.manifest_import import _is_safe_to_delete_source

    assert _is_safe_to_delete_source(Path("/Volumes/Files/x.jpg")) is False
    home_file = Path(os.path.expanduser("~")) / "Documents" / "x.jpg"
    assert _is_safe_to_delete_source(home_file) is True
    # Outside $HOME and not /Volumes — still refuse (conservative).
    assert _is_safe_to_delete_source(Path("/etc/hosts")) is False


def test_import_is_idempotent(client, db, tmp_path):
    manifest = _fixture_manifest(tmp_path)
    adapter = _TestClientAdapter(client)

    first = import_manifest(adapter, manifest, str(tmp_path / "lib.fichero"))
    second = import_manifest(adapter, manifest, str(tmp_path / "lib.fichero"))

    assert first.documents_created == 2
    # Second run skips everything already present.
    assert second.documents_created == 0
    assert second.documents_skipped == 2
    assert second.entities_created == 0
    assert second.entities_reused == 2
    assert second.artifacts_created == 0
    assert second.artifacts_skipped == 4
    assert second.claims_created == 0
    assert second.claims_skipped == 1

    # No duplication on disk.
    docs = client.get("/api/documents?limit=500").json()
    items = docs["items"] if isinstance(docs, dict) else docs
    assert len([d for d in items if d["name"] in {"Tiny Corpus", "page_001"}]) == 2
    claims = client.get("/api/claims?limit=500").json()
    claim_items = claims["items"] if isinstance(claims, dict) else claims
    assert len(claim_items) == 1
    artifacts = client.get("/api/artifacts/?limit=500").json()
    artifact_items = artifacts["items"] if isinstance(artifacts, dict) else artifacts
    imported = [
        a
        for a in artifact_items
        if a["artifact_type"] in {"import_receipt", "transcription", "people", "places"}
    ]
    assert len(imported) == 4


def test_import_skips_processing_for_excluded_existing_document(client, db, tmp_path):
    manifest = _fixture_manifest(tmp_path)
    summary = import_manifest(
        _TestClientAdapter(client),
        manifest,
        str(tmp_path / "lib.fichero"),
    )
    assert summary.documents_created == 2

    docs = client.get("/api/documents?limit=500").json()["items"]
    page = next(d for d in docs if d["name"] == "page_001")

    excluded = db.get(Document, page["id"])
    assert excluded is not None
    excluded.exclude_from_processing = True
    db.save(excluded)

    rerun = import_manifest(
        _TestClientAdapter(client),
        manifest,
        str(tmp_path / "lib.fichero"),
    )

    assert rerun.documents_skipped == 2
    assert rerun.entities_created == 0
    assert rerun.claims_created == 0
    assert rerun.artifacts_created == 0


def test_import_receipt_is_created_even_without_text_or_entities(client, tmp_path):
    manifest = tmp_path / "manifest.jsonl"
    node = {
        "canonical_version": CANONICAL_VERSION,
        "node_type": "page",
        "external_id": "receipt_only__page_001",
        "parent_external_id": None,
        "corpus": "receipt_only",
        "name": "page_001",
        "sequence": 1,
        "page_label": "001",
        "language": "en",
        "text": "",
        "images": [],
        "entities": [],
        "claims": [],
        "metadata": {},
    }
    manifest.write_text(json.dumps(node) + "\n", encoding="utf-8")

    summary = import_manifest(
        _TestClientAdapter(client),
        manifest,
        str(tmp_path / "lib.fichero"),
    )

    assert summary.artifacts_created == 1
    docs = client.get("/api/documents?limit=500").json()
    items = docs["items"] if isinstance(docs, dict) else docs
    page = next(d for d in items if d["name"] == "page_001")
    page_artifacts = client.get(
        f"/api/artifacts/document/{page['id']}?include_descendants=false"
    ).json()
    artifact_types = {a["artifact_type"] for a in page_artifacts["items"]}
    assert artifact_types == {"import_receipt"}
