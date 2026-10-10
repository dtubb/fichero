"""`prep.yolo.fine-tune-from-corrected-regions` (#5525): the regions a person corrected teach a layout model.

Written from the spec: a person's regions (not a model's) become YOLO labels, each region's own label its class,
the held-out pages the validation set; the training runs as a job on this Mac (the real job, lane and scheduler,
with a fake trainer standing in for Ultralytics) and lands the model in the project with its region-overlap
score, where a find-regions step can use it by id.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from PIL import Image

from fichero_server.execution import jobs
from fichero_server.llm import yolo_runtime
from fichero_server.models import DocType, Document, FileType, Status
from fichero_server.training import yolo_local
from fichero_server.training.yolo_set import EmptyRegionSet, export_region_set
from tests.unit.jobs.test_training_on_this_mac import mac  # noqa: F401  (fixture)


def _page(db, tmp_path, name, folder):
    photo = tmp_path / f"{name}.jpg"
    Image.new("RGB", (800, 1200), (230, 225, 210)).save(photo)
    doc = Document(name=photo.name, doc_type=DocType.file, file_type=FileType.image, path=str(photo),
                   parent_id=folder.id, status=Status.completed)
    db.save(doc)
    return doc


def _persons_regions(client, doc, regions):
    """Regions drawn by a person, the way the app saves them: a pass, then its segments."""
    made = client.post("/api/segments/passes", json={"document_id": doc.id, "name": "My regions"})
    assert made.status_code == 200, made.text
    pass_id = made.json()["id"]
    body = {"document_id": doc.id, "pass_id": pass_id, "segments": [
        {"kind": "region", "kind_raw": label, "anchor": {"document_id": doc.id, "rect": rect}}
        for label, rect in regions]}
    r = client.post("/api/segments/bulk", json=body)
    assert r.status_code == 200, r.text


@pytest.fixture
def corrected(client, db, tmp_path):
    folder = Document(name="Notebook", doc_type=DocType.folder)
    db.save(folder)
    first, second = _page(db, tmp_path, "p1", folder), _page(db, tmp_path, "p2", folder)
    _persons_regions(client, first, [("marginal note", [0.02, 0.1, 0.15, 0.6]), ("text-block", [0.2, 0.1, 0.7, 0.8])])
    _persons_regions(client, second, [("text-block", [0.2, 0.1, 0.7, 0.8])])
    return folder, first, second


def test_a_persons_regions_become_labels_and_a_models_do_not(client, db, tmp_path, corrected, monkeypatch):
    from fichero_server.recipes.regions import find_regions

    folder, first, second = corrected
    monkeypatch.setattr(yolo_runtime, "detect_regions", lambda path, model_id=None, **k: [
        yolo_runtime.Region(kind_raw="Picture", rect=[0.0, 0.0, 1.0, 1.0], confidence=0.3)])
    find_regions(db, [first.id], "run-model", "yolo-doclaynet-11n")  # a model's regions: never training data

    made = export_region_set(db, scope_ids=[folder.id], held_out_ids=[second.id], out_dir=tmp_path / "set")

    assert (made.pages, made.regions, made.classes, made.held_out) == (2, 3, ["marginal note", "text-block"],
                                                                       [second.id])
    labels = (tmp_path / "set" / "labels" / "train" / f"{first.id}.txt").read_text().split("\n")
    assert labels[:2] == ["0 0.095000 0.400000 0.150000 0.600000", "1 0.550000 0.500000 0.700000 0.800000"]
    assert (tmp_path / "set" / "images" / "val" / f"{second.id}.jpg").is_file()
    assert "val: images/val" in (tmp_path / "set" / "data.yaml").read_text()


def test_nothing_corrected_is_refused(db, tmp_path):
    folder = Document(name="Untouched", doc_type=DocType.folder)
    db.save(folder)
    _page(db, tmp_path, "p", folder)
    with pytest.raises(EmptyRegionSet):
        export_region_set(db, scope_ids=[folder.id], held_out_ids=[], out_dir=tmp_path / "set")


def test_training_runs_as_a_job_and_lands_in_the_project_for_find_regions(client, db, tmp_path, corrected,
                                                                          mac, monkeypatch):  # noqa: F811
    folder, first, second = corrected
    base = tmp_path / "base.pt"
    base.write_bytes(b"stock weights")
    real_path = yolo_runtime.model_path
    monkeypatch.setattr(yolo_runtime, "model_path",
                        lambda model_id: base if model_id == "yolo-doclaynet-11n" else real_path(model_id))
    trained_with = {}

    def fake_trainer(model_file, data_yaml, out, request, gentle, *, resume):
        trained_with.update(base=model_file, data=Path(data_yaml).read_text())
        for epoch in range(request.epochs):
            gentle.on_batch()
            gentle.on_epoch_end(epoch)
        best = out / "run" / "weights" / "best.pt"
        best.parent.mkdir(parents=True, exist_ok=True)
        best.write_bytes(b"fine-tuned weights")
        return best, {"metrics/mAP50(B)": 0.81}

    monkeypatch.setattr(yolo_local, "TRAINER", fake_trainer)
    r = client.post("/api/training/regions/here", json={"name": "notebook regions", "scope_ids": [folder.id],
                                                         "held_out_ids": [second.id], "epochs": 2})
    assert r.status_code == 200, r.text
    job_id = r.json()["job_id"]
    deadline = time.monotonic() + 60
    while jobs.read_job(db, job_id)["state"] not in ("done", "failed") and time.monotonic() < deadline:
        time.sleep(0.05)
    row = jobs.read_job(db, job_id)
    assert row["state"] == "done", row["reason"]

    model_id = json.loads(row["detail"])["model_id"]
    assert trained_with["base"] == str(base) and "marginal note" in trained_with["data"]
    landed = yolo_runtime.model_path(model_id)
    assert landed is not None and landed.read_bytes() == b"fine-tuned weights"
    card = json.loads((landed.parent / "fichero-card.json").read_text())
    assert card["region_overlap_map50"] == 0.81 and card["scored_on"] == "1 held-out page"
    assert card["classes"] == ["marginal note", "text-block"]


def test_a_base_model_not_on_this_mac_is_refused_before_anything_is_queued(client, db, corrected, monkeypatch):
    folder, _first, _second = corrected
    monkeypatch.setattr(yolo_runtime, "model_path", lambda model_id: None)
    r = client.post("/api/training/regions/here", json={"name": "x", "scope_ids": [folder.id]})
    assert r.status_code == 422 and "download it first" in r.text
