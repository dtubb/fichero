"""A long image operation can be asked for as a job (`image.ops.long-operation-is-a-job`, #6384): the request returns a job id at
once, the images lane runs the SAME audited action, and Activity/Cancel are the job's own."""
from __future__ import annotations

import json
import time

from PIL import Image

from fichero_server.execution import jobs
from fichero_server.image_op_job import KIND, queue_image_operation
from fichero_server.models import ActionAudit, Document, FileType, ImageEditChain


def _page(db) -> Document:
    path = db.path.parent / "files" / "j.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (120, 90), "white").save(path, format="PNG")
    doc = Document(name="j.png", path=str(path), file_type=FileType.image)
    db.save(doc)
    return doc


def _ops(db, doc) -> list[str]:
    chains = list(db.query(ImageEditChain, document_id=doc.id))
    return [op["op"] for op in chains[0].operations] if chains else []


def test_asking_for_a_job_returns_its_id_and_the_job_runs_the_same_action(client, db):
    doc = _page(db)
    got = client.post(f"/api/images/{doc.id}/jobs", json={"action": "image.remove_background", "params": {"method": "threshold"}})
    assert got.status_code == 202, got.text
    job_id = got.json()["job_id"]
    assert jobs.read_job(db, job_id)["kind"] == KIND
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline and jobs.read_job(db, job_id)["state"] not in ("done", "failed"):
        time.sleep(0.1)  # the images lane takes it up
    row = jobs.read_job(db, job_id)
    assert row["state"] == "done", row
    assert json.loads(row["detail"])["action"] == "image.remove_background"
    assert _ops(db, doc) == ["remove_background"]
    assert [a.action_name for a in db.query(ActionAudit)].count("image.remove_background") == 1


def test_a_second_ask_of_the_same_page_is_its_own_job(db):
    doc = _page(db)
    first = queue_image_operation(db, "image.grayscale", {"document_id": doc.id})
    second = queue_image_operation(db, "image.grayscale", {"document_id": doc.id})
    assert first != second


def test_only_an_image_action_on_one_page_is_accepted(client, db):
    doc = _page(db)
    assert client.post(f"/api/images/{doc.id}/jobs", json={"action": "documents.delete"}).status_code == 422
    assert client.post(f"/api/images/{doc.id}/jobs", json={"action": "image.nonsense"}).status_code == 422
    assert client.post(f"/api/images/{doc.id}/jobs", json={"action": "image.rotate", "params": {}}).status_code == 422  # angle is required
    assert client.post("/api/images/nope/jobs", json={"action": "image.grayscale"}).status_code == 404
