"""What the end-to-end onboarding run on real pages found wrong in the engine (#5668, the week plan's top goal:
"onboarding does everything automatically: read, then organise"), each pinned where it was found.

The run (2026-10-11): a scratch engine driven only through the fichero CLI; a project; the 92 pages of
CACIQUES_INDIOS,17,D.5 added with Copy; Set Up's answers and stages; Start; the result read back.
"""

from __future__ import annotations

import pytest
from PIL import Image


def test_a_copy_import_of_a_folder_warns_of_no_page_in_icloud(client, tmp_path):
    """`source.onboard.icloud-pages-warned`: "a folder is never 'a page in iCloud' … pages copied into the
    project are never counted." The run's Copy import of a local folder said "1 page is in iCloud and not on this
    Mac", naming the folder: a directory reports a size with no blocks of its own."""
    box = tmp_path / "CACIQUES_INDIOS,17,D.5"
    box.mkdir()
    for i in range(3):
        Image.new("RGB", (40, 60), (230, 225, 210)).save(box / f"{i + 1}_Hoja_{530 + i}_Recto.JPG")

    started = client.post("/api/ingest/folder", json={"path": str(box), "mode": "copy"})
    assert started.status_code == 200, started.text
    status = client.get(f"/api/ingest/status/{started.json()['task_id']}").json()

    assert status["status"] == "completed", status
    assert status["in_icloud"] is None, status["in_icloud"]


def test_find_regions_looks_at_pages_copied_into_the_project(db, monkeypatch):
    """`prep.regions.open-default`: "Every page the project holds is looked at, whether copied into the project (its
    path inside the package) or linked." The run's Find Regions said all 92 copied pages had no image: it opened
    the stored package-relative path (`files/…`) as it stood."""
    from pathlib import Path

    from fichero_server.llm import kraken_runtime
    from fichero_server.models import DocType, Document, FileType
    from fichero_server.recipes.regions import find_regions

    library = Path(db.path).parent
    stored = Path("files") / "ab" / "1_Hoja_530_Recto.JPG"
    (library / stored).parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (100, 200), (230, 225, 210)).save(library / stored, format="JPEG")
    page = Document(name="1_Hoja_530_Recto.JPG", doc_type=DocType.file, file_type=FileType.image, path=str(stored))
    db.save(page)
    opened = []
    monkeypatch.setattr(kraken_runtime, "segment_lines", lambda path, **k: opened.append(path) or {
        "width": 100, "height": 200, "lines": [],
        "regions": [{"id": "r1", "type": "text", "polygon": [[10, 20], [90, 20], [90, 180], [10, 180]]}]})

    account = find_regions(db, [page.id], "run-1", "blla", provider="kraken")

    assert account == {"pages": 1, "regions": 1, "no_image": 0}
    assert opened == [str(library / stored)]


def test_apple_vision_used_for_read_a_page_is_what_start_runs():
    """`source.find.used-candidate-runs`: "A candidate the finder lists as runnable on this Mac, once used for the
    step, is what Start runs." The run chose Apple Vision for Read a page (the no-download reader); Start skipped
    the step, "Transcribe HTR cannot run the model {'builtin': 'apple-vision'}"."""
    from fichero_server.recipes.start import plan_start

    recipe = {"fichero_recipe": 1, "id": "t/r", "version": "0.1.0", "title": "t", "steps": [
        {"id": "read-a-page", "job": "read-a-page", "model": {"builtin": "apple-vision"}}]}

    plan = plan_start(recipe, stays_local=True)

    assert plan["skipped"] == [] and plan["refusals"] == [], (plan["skipped"], plan["refusals"])
    (run,) = plan["workflows"]
    assert (run["provider_override"], run["model_override"]) == ("apple", "apple-vision")
    assert run["runs_on"] == "this-mac"


@pytest.mark.parametrize("vision_mode", ["apple", "llm"])  # "llm": Transcribe HTR runs Apple as its provider
def test_apple_finding_no_text_on_a_page_is_not_a_failed_read(tmp_path, monkeypatch, vision_mode):
    """`source.recipe.no-text-found-is-not-a-failure`: the run counted 5 pages Apple Vision found no text on as
    failed reads, "Vision LLM returned no transcription … try a stronger vision model", and offered to read them
    again."""
    import asyncio
    from unittest.mock import patch

    from fichero_server.db.manager import db_manager
    from fichero_server.llm import LLMConfig
    from fichero_server.workflows.tools.vision_base import VisionOCRResult
    from fichero_server.models import DocType, Document, FileType
    from fichero_server.workflows.tools.sources import files_tool
    from fichero_server.workflows.tools.transcribe import transcribe

    monkeypatch.setenv("FICHERO_SKIP_DEFAULT_WORKFLOWS", "1")
    library = tmp_path / "Blank.fichero"
    library.mkdir()
    db = db_manager.get_database(str(library))
    png = tmp_path / "22_Hoja_540_Verso.png"
    Image.new("RGB", (16, 16), (255, 255, 255)).save(png)
    doc = Document(name=png.name, doc_type=DocType.file, file_type=FileType.image, path=str(png))
    db.save(doc)
    config = LLMConfig(provider="apple", model="apple-vision")

    async def read():
        src = await files_tool(inputs={}, state={"selected_doc_ids": [doc.id], "library_path": str(library)},
                               llm_config=config)
        with patch("fichero_server.workflows.tools.vision_base.apple_vision_ocr_with_geometry",
                   return_value=VisionOCRResult(text="", line_boxes=[], word_boxes=[])):
            return await transcribe(inputs={"files": src["files"], "documents": src["documents"],
                                            "vision_mode": vision_mode},
                                    state={"library_path": str(library), "task_id": None}, llm_config=config)

    try:
        result = asyncio.run(read())
    finally:
        db_manager.close_all()

    said = str(result)
    assert "returned no transcription" not in said and "stronger vision model" not in said, said
    assert not [r for r in result.get("results") or [] if r.get("error")], result.get("results")
    assert "found no text" in said, said


# --- source.pages.image-found-wherever-kept ----------------------------------------------------------------------


def _copied(db, name: str, *, written: bool, folder=None, sequence: int = 1, faded: bool = False):
    """A page copied into the project: its image inside the package, its stored path package-relative."""
    from pathlib import Path

    from PIL import ImageDraw

    from fichero_server.models import DocType, Document, FileType

    library = Path(db.path).parent
    stored = Path("files") / "cd" / name
    (library / stored).parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (400, 600), (205, 200, 190) if faded else (235, 230, 220))
    if written:
        draw = ImageDraw.Draw(image)
        for y in range(40, 560, 18):
            draw.line([(30, y), (370, y)], fill=(150, 145, 140) if faded else (20, 20, 20), width=4)
    image.save(library / stored, format="JPEG")
    page = Document(name=name, doc_type=DocType.file, file_type=FileType.image, path=str(stored),
                    parent_id=folder.id if folder else None, sequence=sequence)
    db.save(page)
    return page, library / stored


def test_the_blank_verso_rule_and_the_image_cues_see_copied_pages(db):
    """"… the blank versos were sent to Apple Vision (the blank-verso rule saw no image), and Find the Documents
    worked from the text alone": both now look at a copied page's image."""
    from fichero_server.finddocs.job import blank_versos, page_inputs
    from fichero_server.models import DocType, Document

    folder = Document(name="CACIQUES", doc_type=DocType.folder)
    db.save(folder)
    recto, _ = _copied(db, "1_Hoja_530_Recto.JPG", written=True, folder=folder, sequence=1)
    blank, _ = _copied(db, "2_Hoja_en_blanco.jpg", written=False, folder=folder, sequence=2)

    assert blank_versos(db, [recto.id, blank.id]) == {blank.id}
    inputs = {p.id: p for p in page_inputs(db, [recto, blank])}
    assert inputs[recto.id].ink is not None and inputs[recto.id].image_hash is not None


def test_prepare_images_looks_at_copied_pages(db):
    from fichero_server.recipes.prepare import prepare_pages

    faded, _ = _copied(db, "3_Hoja_531_Recto.JPG", written=True, faded=True)
    account = prepare_pages(db, [faded.id], "run-1")
    assert account["no_image"] == 0, account


def test_the_bake_offs_reference_page_finds_a_copied_photograph(db, monkeypatch):
    """The evaluation said "its photograph is not on this Mac" for every copied page, and named the stored path."""
    from types import SimpleNamespace

    from fichero_server import page_export
    from fichero_server.training import evaluation

    page, photo = _copied(db, "4_Hoja_531_Verso.JPG", written=True)
    monkeypatch.setattr(evaluation, "checked_pass", lambda db, page_id, checked: SimpleNamespace(id="pass-1"))
    monkeypatch.setattr(evaluation, "trust_of", lambda chosen: "person")
    monkeypatch.setattr(page_export, "export_page", lambda *a, **k: SimpleNamespace(data=b"<PcGts/>"))
    monkeypatch.setattr("fichero_server.checking.line_check.page_lines",
                        lambda xml: [{"id": "l1", "text": "Muy señor mío"}])

    reference, why = evaluation.reference_page(db, page.id, "person")

    assert why is None, why
    assert reference["photo"] == str(photo)


def test_the_regions_training_set_takes_copied_pages(db, tmp_path, monkeypatch):
    from types import SimpleNamespace

    from fichero_server.training import kraken_set, yolo_set

    page, _ = _copied(db, "5_Hoja_532_Recto.JPG", written=True)
    box = SimpleNamespace(bbox_x=0.1, bbox_y=0.1, bbox_w=0.5, bbox_h=0.3)
    monkeypatch.setattr(kraken_set, "pages_in_scope", lambda db, scope_ids: [page])
    monkeypatch.setattr(yolo_set, "persons_regions", lambda db, document_id: [box])
    monkeypatch.setattr(yolo_set, "label_of", lambda segment: "text")

    made = yolo_set.export_region_set(db, scope_ids=[page.id], held_out_ids=[], out_dir=tmp_path / "set")

    assert made.pages == 1 and (tmp_path / "set" / "images" / "train" / f"{page.id}.jpg").is_file()
