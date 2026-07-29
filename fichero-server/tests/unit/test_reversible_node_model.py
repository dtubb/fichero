"""Cross-cutting reversible node-model invariants (#3553)."""

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

import httpx
import pytest
from PIL import Image

from fichero_server.api.auth import initialize_token
from fichero_server.api.main import app
from fichero_server.models import DocType, Document, FileType


def _source(db, name: str = "source.png", size: tuple[int, int] = (100, 80)) -> Document:
    path = db.path.parent / "files" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", size, "white")
    image.putpixel((0, 0), (255, 0, 0))
    image.save(path, format="PNG")
    document = Document(name=name, path=str(path), file_type=FileType.image)
    db.save(document)
    return document


def _hash(document: Document) -> str:
    return hashlib.sha256(Path(document.path).read_bytes()).hexdigest()


def test_split_unsplit_crop_uncrop_and_group_ungroup_round_trips(client, db):
    left_parent = Document(name="Left", doc_type=DocType.folder)
    right_parent = Document(name="Right", doc_type=DocType.folder)
    first = Document(name="First", parent_id=left_parent.id, sort_order=3)
    second = Document(name="Second", parent_id=right_parent.id, sort_order=7)
    for document in (left_parent, right_parent, first, second):
        db.save(document)

    grouped = client.post(
        "/api/documents/groups", json={"name": "Letter", "child_ids": [first.id, second.id]}
    )
    assert grouped.status_code == 200
    assert client.post(f"/api/documents/groups/{grouped.json()['id']}/ungroup").status_code == 200
    assert db.get(Document, first.id).parent_id == left_parent.id
    assert db.get(Document, first.id).sort_order == 3
    assert db.get(Document, second.id).parent_id == right_parent.id
    assert db.get(Document, second.id).sort_order == 7

    source = _source(db)
    source_before = db.get(Document, source.id).model_dump(mode="json")
    digest_before = _hash(source)
    split = client.post(
        f"/api/images/{source.id}/split",
        json={"bboxes": [[0, 0, 50, 80], [50, 0, 50, 80]]},
    )
    assert split.status_code == 200
    children = split.json()["children"]
    assert client.post(f"/api/images/{source.id}/unsplit").status_code == 200
    assert all(db.get(Document, child["id"]).deleted_at is not None for child in children)

    crop = client.post(
        f"/api/images/{source.id}/crop",
        json={"left": 10, "top": 10, "width": 30, "height": 30},
    )
    assert crop.status_code == 200
    crop_child = crop.json()["child"]
    assert client.post(f"/api/images/{crop_child['id']}/uncrop").status_code == 200
    assert db.get(Document, crop_child["id"]).deleted_at is not None
    assert db.get(Document, source.id).model_dump(mode="json") == source_before
    assert _hash(source) == digest_before


def test_nested_reverse_lifo_restores_root_and_source_bytes(client, db):
    source = _source(db, "nested.png")
    source_before = db.get(Document, source.id).model_dump(mode="json")
    digest_before = _hash(source)

    split = client.post(
        f"/api/images/{source.id}/split",
        json={"bboxes": [[0, 0, 50, 80], [50, 0, 50, 80]]},
    )
    assert split.status_code == 200
    left, right = split.json()["children"]
    crop = client.post(
        f"/api/images/{left['id']}/crop",
        json={"left": 5, "top": 5, "width": 20, "height": 30},
    )
    assert crop.status_code == 200
    group = client.post(
        "/api/documents/groups", json={"name": "Spread", "child_ids": [left["id"], right["id"]]}
    )
    assert group.status_code == 200

    assert client.post(f"/api/documents/groups/{group.json()['id']}/ungroup").status_code == 200
    assert client.post(f"/api/images/{crop.json()['child']['id']}/uncrop").status_code == 200
    assert client.post(f"/api/images/{source.id}/unsplit").status_code == 200
    assert db.get(Document, source.id).model_dump(mode="json") == source_before
    assert _hash(source) == digest_before
    assert all(db.get(Document, child["id"]).deleted_at is not None for child in (left, right))


def test_reversible_node_guards_raise(client, db):
    source = _source(db, "guards.png")
    assert client.post(f"/api/images/{source.id}/split", json={"bboxes": []}).status_code == 422
    assert client.post(
        f"/api/images/{source.id}/crop",
        json={"left": 90, "top": 0, "width": 20, "height": 10},
    ).status_code == 422
    assert client.post(f"/api/documents/groups/{source.id}/ungroup").status_code == 404
    assert client.post(f"/api/images/{source.id}/unsplit").status_code == 404

    crop = client.post(
        f"/api/images/{source.id}/crop",
        json={"left": 0, "top": 0, "width": 10, "height": 10},
    )
    child_id = crop.json()["child"]["id"]
    assert client.post(f"/api/images/{child_id}/uncrop").status_code == 200
    assert client.post(f"/api/images/{child_id}/uncrop").status_code == 404


@pytest.mark.anyio
async def test_interleaved_crop_and_group_preserve_membership(db, test_package):
    source = _source(db, "concurrent.png")
    transport = httpx.ASGITransport(app=app)
    headers = {
        "X-Fichero-Library-Path": str(test_package),
        "Authorization": f"Bearer {initialize_token()}",
    }
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver", headers=headers
    ) as client:
        split = await client.post(
            f"/api/images/{source.id}/split",
            json={"bboxes": [[0, 0, 50, 80], [50, 0, 50, 80]]},
        )
        left, right = split.json()["children"]

        # ponytail: Database's process-wide RLock serializes statements, not an
        # entire workflow; add per-source transactional coordination only if
        # conflicting multi-request edits need stronger semantics.
        crop, group = await asyncio.gather(
            client.post(
                f"/api/images/{left['id']}/crop",
                json={"left": 5, "top": 5, "width": 20, "height": 20},
            ),
            client.post(
                "/api/documents/groups",
                json={"name": "Concurrent spread", "child_ids": [left["id"], right["id"]]},
            ),
        )

    assert crop.status_code == 200
    assert group.status_code == 200
    group_document = db.get(Document, group.json()["id"])
    assert {member["id"] for member in group_document.metadata["group_members"]} == {
        left["id"],
        right["id"],
    }
    assert db.get(Document, crop.json()["child"]["id"]).parent_id == left["id"]
