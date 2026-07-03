from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from fichero import __main__ as cli
from fichero.iiif_import import import_iiif, parse_iiif_directory


class _TestClientAdapter:
    """Adapt FastAPI TestClient to the importer client protocol."""

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
        else:  # pragma: no cover
            raise AssertionError(f"unexpected method {method}")
        if method == "GET" and path.startswith("/storage/") and resp.status_code >= 400:
            return None
        assert resp.status_code < 400, (method, url, resp.status_code, resp.text)
        if not resp.content:
            return None
        try:
            return resp.json()
        except ValueError:
            return None


def _write_tiny_iiif(tmp_path: Path) -> Path:
    image = tmp_path / "page_001.jpg"
    image.write_bytes(b"not-a-real-image")
    canvas_id = "https://example.org/iiif/canvas/page-001"
    annotation_page = {
        "@context": "http://www.w3.org/ns/anno.jsonld",
        "id": "annotations/page-001.json",
        "type": "AnnotationPage",
        "items": [
            {
                "id": "https://example.org/anno/entity-1",
                "type": "Annotation",
                "motivation": "tagging",
                "body": {
                    "id": "https://example.org/entity/marshall",
                    "type": "TextualBody",
                    "value": "Marshall",
                    "entity_type": "person",
                },
                "target": {
                    "source": canvas_id,
                    "selector": {
                        "type": "TextPositionSelector",
                        "start": 0,
                        "end": 8,
                    },
                },
            },
            {
                "id": "https://example.org/anno/date-1",
                "type": "Annotation",
                "motivation": "describing",
                "body": {
                    "type": "TextualBody",
                    "value": "Diary entry dated 1923-02-05",
                },
                "target": {
                    "source": canvas_id,
                    "selector": {
                        "type": "TextQuoteSelector",
                        "exact": "Marshall went",
                    },
                },
            },
        ],
    }
    manifest = {
        "@context": "http://iiif.io/api/presentation/3/context.json",
        "id": "https://example.org/iiif/manifest/tiny",
        "type": "Manifest",
        "label": {"en": ["Tiny Diary"]},
        "navDate": "1923-02-05T00:00:00Z",
        "metadata": [
            {"label": {"en": ["Date"]}, "value": {"en": ["1923-02-05"]}},
        ],
        "items": [
            {
                "id": canvas_id,
                "type": "Canvas",
                "label": {"en": ["Page 001"]},
                "height": 1000,
                "width": 700,
                "items": [
                    {
                        "id": "https://example.org/iiif/page/page-001/painting",
                        "type": "AnnotationPage",
                        "items": [
                            {
                                "id": "https://example.org/iiif/anno/painting",
                                "type": "Annotation",
                                "motivation": "painting",
                                "body": {
                                    "id": str(image),
                                    "type": "Image",
                                    "format": "image/jpeg",
                                    "height": 1000,
                                    "width": 700,
                                },
                                "target": canvas_id,
                            },
                            {
                                "id": "https://example.org/iiif/anno/transcript",
                                "type": "Annotation",
                                "motivation": "supplementing",
                                "body": {
                                    "type": "TextualBody",
                                    "format": "text/plain",
                                    "value": "Marshall went to Istmina.",
                                },
                                "target": canvas_id,
                            },
                        ],
                    }
                ],
                "annotations": [{"id": "annotations/page-001.json", "type": "AnnotationPage"}],
            }
        ],
    }
    collection = {
        "@context": "http://iiif.io/api/presentation/3/context.json",
        "id": "https://example.org/iiif/collection/tiny",
        "type": "Collection",
        "label": {"en": ["Tiny Collection"]},
        "items": [
            {
                "id": "https://example.org/iiif/manifest/tiny",
                "type": "Manifest",
            }
        ],
    }
    (tmp_path / "annotations").mkdir()
    (tmp_path / "collection.json").write_text(json.dumps(collection), encoding="utf-8")
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (tmp_path / "annotations" / "page-001.json").write_text(
        json.dumps(annotation_page), encoding="utf-8"
    )
    return tmp_path


def test_parse_iiif_directory_normalizes_nodes_and_annotation_jobs(tmp_path):
    root = _write_tiny_iiif(tmp_path)

    parsed = parse_iiif_directory(root)

    assert parsed.manifests_seen == 1
    assert len(parsed.nodes) == 2
    page = parsed.nodes[-1]
    assert page["node_type"] == "page"
    assert page["text"] == "Marshall went to Istmina."
    assert page["images"][0]["source_path"] == str(tmp_path / "page_001.jpg")
    assert page["entities"][0]["canonical_name"] == "Marshall"
    assert len(parsed.annotation_jobs) == 2


def test_import_iiif_scopes_entities_to_page_and_preserves_text_annotations(
    client, tmp_path
):
    root = _write_tiny_iiif(tmp_path)
    adapter = _TestClientAdapter(client)

    summary = import_iiif(adapter, root, str(tmp_path / "Tiny.fichero"))

    assert summary.manifests_seen == 1
    assert summary.pages_seen == 1
    assert summary.documents_created == 2
    assert summary.artifacts_created == 1
    assert summary.entities_created == 1
    assert summary.annotations_created == 2

    docs = client.get("/api/documents?limit=500").json()["items"]
    page = next(doc for doc in docs if doc["name"] == "Page 001")
    assert page["page_content"] == "Marshall went to Istmina."
    artifacts = client.get(
        f"/api/artifacts/document/{page['id']}",
        params={"artifact_type": "transcription", "include_descendants": False},
    ).json()["items"]
    assert len(artifacts) == 1
    assert artifacts[0]["content"] == "Marshall went to Istmina."
    assert artifacts[0]["provider"] == "iiif-import"
    assert artifacts[0]["model"] == "w3c-annotation"
    assert artifacts[0]["data"]["source"] == "iiif_w3c"
    assert artifacts[0]["data"]["canonical_external_id"] == (
        "https__example.org__iiif__canvas__page-001"
    )

    page_entities = client.get(f"/api/entities?document_id={page['id']}&limit=500").json()[
        "items"
    ]
    assert [entity["canonical_name"] for entity in page_entities] == ["Marshall"]
    assert page["id"] in page_entities[0]["source_document_ids"]

    annotations = client.get(f"/api/annotations?document_id={page['id']}").json()["items"]
    by_id = {ann["metadata"]["w3c_annotation_id"]: ann for ann in annotations}
    entity_ann = by_id["https://example.org/anno/entity-1"]
    assert entity_ann["char_start"] == 0
    assert entity_ann["char_end"] == 8
    assert entity_ann["linked_entity_ids"] == [page_entities[0]["id"]]
    assert "tagging" in entity_ann["tags"]

    summary2 = import_iiif(adapter, root, str(tmp_path / "Tiny.fichero"))
    assert summary2.documents_skipped == 2
    assert summary2.artifacts_skipped == 1
    assert summary2.annotations_skipped == 2
    artifacts2 = client.get(
        f"/api/artifacts/document/{page['id']}",
        params={"artifact_type": "transcription", "include_descendants": False},
    ).json()["items"]
    assert len(artifacts2) == 1


def test_cli_import_iiif_invokes_importer(monkeypatch, tmp_path):
    called: dict[str, Any] = {}

    def fake_import(**kwargs):
        called.update(kwargs)
        from fichero.iiif_import import IIIFImportSummary

        return IIIFImportSummary(
            iiif=str(kwargs["iiif_path"]),
            library_path=str(kwargs["library_path"]),
            manifests_seen=1,
            pages_seen=1,
        )

    monkeypatch.setattr("fichero.iiif_import.import_iiif_via_http", fake_import)
    runner = CliRunner()
    result = runner.invoke(
        cli.app,
        [
            "--base-url",
            "http://remote-engine.test",
            "import-iiif",
            "--iiif",
            str(tmp_path),
            "--library",
            str(tmp_path / "Tiny.fichero"),
            "--ingest",
            "copy",
        ],
    )

    assert result.exit_code == 0
    assert called["iiif_path"] == tmp_path
    assert called["library_path"] == tmp_path / "Tiny.fichero"
    assert called["client"].base_url == "http://remote-engine.test"
    assert called["ingest_mode"] == "copy"
