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

from fichero.manifest_import import import_manifest, validate_nodes


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
        else:  # pragma: no cover - importer only uses GET/POST
            raise AssertionError(f"unexpected method {method}")
        assert resp.status_code < 400, (method, url, resp.status_code, resp.text)
        if resp.content:
            return resp.json()
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
    # Image is referenced (path points at the existing source file), not copied.
    assert page["path"] == str(tmp_path / "page_001_enhanced.jpg")
    assert Path(page["path"]).exists()
    # Renditions preserved in metadata.
    assert page["metadata"]["canonical_external_id"] == "tiny_corpus__page_001"
    assert page["metadata"]["images"][0]["role"] == "enhanced"

    entities = client.get("/api/entities?limit=500").json()
    ent_items = entities["items"] if isinstance(entities, dict) else entities
    names = {e["canonical_name"] for e in ent_items}
    assert {"Marshall", "Istmina"} <= names

    claims = client.get("/api/claims?limit=500").json()
    claim_items = claims["items"] if isinstance(claims, dict) else claims
    assert len(claim_items) == 1
    claim = claim_items[0]
    assert claim["text"] == "Marshall went to Istmina"
    # Claim links to both entities (resolved from entity_refs -> ids).
    assert len(claim["entity_ids"]) == 2
    assert claim["source_document_id"] == page["id"]


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
    assert second.claims_created == 0
    assert second.claims_skipped == 1

    # No duplication on disk.
    docs = client.get("/api/documents?limit=500").json()
    items = docs["items"] if isinstance(docs, dict) else docs
    assert len([d for d in items if d["name"] in {"Tiny Corpus", "page_001"}]) == 2
    claims = client.get("/api/claims?limit=500").json()
    claim_items = claims["items"] if isinstance(claims, dict) else claims
    assert len(claim_items) == 1
