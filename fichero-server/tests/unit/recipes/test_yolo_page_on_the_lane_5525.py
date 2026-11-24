"""A YOLO page of Find Regions runs as a job on the local ML lane, as a Kraken page does (#5525).

Spec: docs/contributor_manual/specs/ai/local-runtimes.md Step 2.1 (`runtime.yolo.none-yet`: "it runs in the recipe's
own job rather than as a job on the local ML lane, so it does not yet take its turn with the other heavy models"). The
detector is stubbed at its one seam (`yolo_runtime.detect_regions`); the lane at `jobs.run_on_lane_blocking`.
"""
from __future__ import annotations

from PIL import Image

from fichero_server.execution import jobs
from fichero_server.llm import yolo_runtime
from fichero_server.models import DocType, Document, FileType

MODEL = "yolo-doclaynet-11n"


def test_a_yolo_page_is_handed_to_the_model_lane_under_its_model(db, tmp_path, monkeypatch):
    from fichero_server.recipes.regions import find_regions

    photo = tmp_path / "page.png"
    Image.new("RGB", (600, 800), (230, 225, 210)).save(photo)
    page = Document(name="page.png", doc_type=DocType.file, file_type=FileType.image, path=str(photo))
    db.save(page)
    on_lane: list[dict] = []
    inside = {"now": False}
    found_inside: list[bool] = []

    def lane(library, kind, subject, *, fn, **kw):
        on_lane.append({"kind": kind, "subject": subject, **kw})
        inside["now"] = True
        try:
            return fn()
        finally:
            inside["now"] = False

    def detect(path, model_id=MODEL, **_):
        found_inside.append(inside["now"])
        return [yolo_runtime.Region(kind_raw="Text", rect=[0.1, 0.1, 0.8, 0.3], confidence=0.9)]

    monkeypatch.setattr(jobs, "run_on_lane_blocking", lane)
    monkeypatch.setattr(yolo_runtime, "is_installed", lambda model_id: True)
    monkeypatch.setattr(yolo_runtime, "detect_regions", detect)

    account = find_regions(db, [page.id], "run-1", MODEL)

    assert account["regions"] == 1
    assert found_inside == [True], "the detector ran outside the lane"
    (call,) = on_lane
    assert (call["kind"], call["subject"], call["model"]) == ("find-regions", page.id, f"yolo:{MODEL}")
    assert call["parent_id"] == "run-1" and call["run_id"] == "run-1"
