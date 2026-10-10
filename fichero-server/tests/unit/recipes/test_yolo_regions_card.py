"""`prep.yolo.regions-card` (#5525): a recipe's `find-regions` step has a YOLO card.

Written from the spec, not the code: the step runs a YOLO layout model on each page image and its regions land in
the page model as a machine's regions (provider `yolo`, the model named), each with the model's own label; the
model is downloaded on request, so Start offers it when it is not on this Mac; and the step is no longer sent to
"Detect Segments by hand". The model itself is stubbed at its one seam (`yolo_runtime.detect_regions`).
"""

from __future__ import annotations

from PIL import Image

from fichero_server.llm import yolo_runtime
from fichero_server.models import Artifact, DocType, Document, FileType, Status
from tests.unit.recipes.test_recipe_execution_to_spec import _recipe, _save

MODEL = "yolo-doclaynet-11n"
REGIONS = {"id": "regions", "job": "find-regions", "model": {"yolo": MODEL}}


def test_start_runs_find_regions_with_yolo_and_offers_the_model_when_it_is_not_here(client, tmp_path, monkeypatch):
    monkeypatch.setattr(yolo_runtime, "is_installed", lambda model_id: False)
    _save(client, _recipe(tmp_path, REGIONS))
    plan = client.get("/api/recipes/project/start").json()

    assert [(r["card"], r.get("model")) for r in plan["runs"] if "regions" in r["steps"]] == [("regions", MODEL)]
    (offer,) = plan["downloads"]
    assert offer["action"] == "model.download" and offer["params"] == {"runtime": "yolo", "model": MODEL}
    assert not any("Detect Segments" in str(s) for s in plan.get("skipped") or [])


def test_an_installed_yolo_model_is_not_offered(client, tmp_path, monkeypatch):
    monkeypatch.setattr(yolo_runtime, "is_installed", lambda model_id: True)
    _save(client, _recipe(tmp_path, REGIONS))
    assert client.get("/api/recipes/project/start").json()["downloads"] == []


def test_the_regions_land_as_a_machines_regions_with_yolos_labels(client, db, tmp_path, monkeypatch):
    from fichero_server.recipes.regions import find_regions

    photo = tmp_path / "page.jpg"
    Image.new("RGB", (1000, 2000), (230, 225, 210)).save(photo)
    page = Document(name="page.jpg", doc_type=DocType.file, file_type=FileType.image, path=str(photo),
                    status=Status.completed)
    text_only = Document(name="notes.txt", page_content="no image here")
    db.save(page)
    db.save(text_only)
    found = [yolo_runtime.Region(kind_raw="Table", rect=[0.1, 0.5, 0.8, 0.3], confidence=0.9),
             yolo_runtime.Region(kind_raw="Section-header", rect=[0.1, 0.05, 0.8, 0.05], confidence=0.8)]
    monkeypatch.setattr(yolo_runtime, "detect_regions", lambda path, model_id=MODEL, **k: found)

    account = find_regions(db, [page.id, text_only.id], "run-1", MODEL)

    assert account == {"pages": 1, "regions": 2, "no_image": 1}
    (art,) = db.query(Artifact, document_id=page.id)
    assert (art.provider, art.model, art.artifact_type) == ("yolo", MODEL, "regions")
    body = client.get(f"/api/segments/document/{page.id}").json()
    (layer,) = [p for p in body["passes"] if p.get("model") == MODEL]
    assert layer["provenance_kind"] != "human"
    regions = [s for s in body["segments"] if s["pass_id"] == layer["id"]]
    assert sorted((s["kind"], s["kind_raw"]) for s in regions) == [("region", "Section-header"), ("region", "Table")]


def test_a_models_boxes_become_page_fractions_in_reading_order():
    regions = yolo_runtime.regions_from(
        {0: "Text", 8: "Table"}, [(8, 0.9, [100, 1000, 900, 1600]), (0, 0.7, [100, 100, 900, 400])], 1000, 2000)
    assert [(r.kind_raw, r.rect, r.confidence) for r in regions] == [
        ("Text", [0.1, 0.05, 0.8, 0.15], 0.7), ("Table", [0.1, 0.5, 0.8, 0.3], 0.9)]


def test_only_a_known_layout_model_is_downloadable(db):
    import pytest

    from fichero_server.llm.local_models import enqueue_download

    with pytest.raises(ValueError, match="not a layout model"):
        enqueue_download(db, "yolo", "some-other-model")
    assert enqueue_download(db, "yolo", MODEL)
