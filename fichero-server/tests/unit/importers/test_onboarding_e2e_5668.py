"""What the end-to-end onboarding run on real pages found wrong in the engine (#5668, the week plan's top goal:
"onboarding does everything automatically: read, then organise"), each pinned where it was found.

The run (2026-10-11): a scratch engine driven only through the fichero CLI; a project; the 92 pages of
CACIQUES_INDIOS,17,D.5 added with Copy; Set Up's answers and stages; Start; the result read back.
"""

from __future__ import annotations

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
