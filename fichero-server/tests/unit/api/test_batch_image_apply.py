"""Batch application of the reversible image-node operations (#3557)."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from PIL import Image

from fichero_server.api.routes.workflow import batch as batch_routes
from fichero_server.models import DocType, Document, FileType
from fichero_server.execution.batch import BatchManager


def _image(db, folder: Document, name: str) -> Document:
    path = db.path.parent / "files" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (100, 80), "white").save(path, format="PNG")
    document = Document(
        name=name, parent_id=folder.id, path=str(path), file_type=FileType.image
    )
    db.save(document)
    return document


def _hash(document: Document) -> str:
    return hashlib.sha256(Path(document.path).read_bytes()).hexdigest()


@pytest.fixture
def batch_manager(tmp_path, monkeypatch):
    manager = BatchManager(str(tmp_path / "batch-apply.duckdb"))
    monkeypatch.setattr(batch_routes, "_batch_manager", manager)
    return manager


def test_batch_crop_creates_one_child_per_image_and_undo_restores_all(
    client, db, batch_manager
):
    folder = Document(name="Images", doc_type=DocType.folder)
    db.save(folder)
    sources = [_image(db, folder, "one.png"), _image(db, folder, "two.png")]
    source_rows = [db.get(Document, source.id).model_dump(mode="json") for source in sources]
    source_hashes = [_hash(source) for source in sources]

    applied = client.post(
        "/api/images/batch-apply",
        json={
            "folder_id": folder.id,
            "operation": "crop",
            "bbox": [10, 10, 50, 40],
        },
    )
    assert applied.status_code == 200
    payload = applied.json()
    assert payload["status"] == "completed"
    assert [item["status"] for item in payload["items"]] == ["completed", "completed"]
    child_ids = [item["inputs"]["child_ids"][0] for item in payload["items"]]
    assert {db.get(Document, child_id).derived_from for child_id in child_ids} == {
        source.id for source in sources
    }
    assert all(db.get(Document, child_id).bbox == (10, 10, 50, 40) for child_id in child_ids)
    assert [db.get(Document, source.id).model_dump(mode="json") for source in sources] == source_rows
    assert [_hash(source) for source in sources] == source_hashes

    undone = client.post(f"/api/images/batch-apply/{payload['batch_id']}/undo")
    assert undone.status_code == 200
    assert set(undone.json()["deleted_child_ids"]) == set(child_ids)
    assert all(db.get(Document, child_id).deleted_at is not None for child_id in child_ids)


def test_batch_split_dispatches_existing_split_primitive(client, db, batch_manager):
    folder = Document(name="Images", doc_type=DocType.folder)
    db.save(folder)
    source = _image(db, folder, "spread.png")

    applied = client.post(
        "/api/images/batch-apply",
        json={
            "folder_id": folder.id,
            "operation": "split",
            "bboxes": [[0, 0, 100, 80]],
        },
    )
    assert applied.status_code == 200
    child_id = applied.json()["items"][0]["inputs"]["child_ids"][0]
    assert db.get(Document, child_id).derived_from == source.id
    assert db.get(Document, child_id).bbox == (0, 0, 100, 80)


def test_batch_item_failure_isolated_to_bad_image(client, db, batch_manager):
    folder = Document(name="Images", doc_type=DocType.folder)
    db.save(folder)
    good = _image(db, folder, "good.png")
    bad = Document(
        name="missing.png",
        parent_id=folder.id,
        path=str(db.path.parent / "files" / "missing.png"),
        file_type=FileType.image,
    )
    db.save(bad)

    applied = client.post(
        "/api/images/batch-apply",
        json={
            "folder_id": folder.id,
            "operation": "crop",
            "bbox": [10, 10, 50, 40],
        },
    )
    assert applied.status_code == 200
    items = applied.json()["items"]
    assert applied.json()["status"] == "partial_failure"
    completed = next(item for item in items if item["status"] == "completed")
    failed = next(item for item in items if item["status"] == "failed")
    assert failed["error"]
    assert db.get(Document, completed["inputs"]["child_ids"][0]).derived_from == good.id
