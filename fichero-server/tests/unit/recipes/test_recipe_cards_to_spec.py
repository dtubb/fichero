"""The split and vision-reading cards, and steps already done (#5390), tested to the spec
(docs/contributor_manual/specs/source/models-chains-and-projects.md): `source.recipe.start-runs-the-steps` (its
`Split Pages` and `Read Lines (Kraken lines, vision model)` cards) and `source.recipe.done-is-not-redone`.

Through the project routes, the readings route and the real scheduler. Stubbed only at the model boundary: Kraken's
line finder and reader (its runtime), the vision model (`llm.vision`), and Apple Vision's outline (which finds no
outline here, so the split works on the whole frame, as it does when Apple Vision is unavailable).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from fichero_server.models import Document, Segment
from tests.unit.recipes.test_recipe_execution_to_spec import (  # noqa: F401  (fixtures)
    _finished,
    _recipe,
    _save,
    _start,
    engine,
    pages,  # noqa: F811
)

GEMINI = {"cloud": "openrouter", "model": "google/gemini-3-flash-preview"}
LINES = {"id": "lines", "job": "find-lines", "model": {"kraken": "blla", "kraken_version": "bundled"}}
READ_WITH_GEMINI = {"id": "read", "job": "read-a-line", "model": GEMINI, "runs_on": "cloud:openrouter"}
KRAKEN_READ = {"id": "read", "job": "read-a-line", "model": {"zenodo": "10.5281/zenodo.13788177"}}
SPLIT = {"id": "split", "job": "split-pages", "model": {"builtin": "page-splitter"}}


class Lines:
    """Kraken's line finder (two lines on any page) and a vision model that reads each line it is shown."""

    def __init__(self):
        self.found: list[str] = []
        self.read_calls = 0

    def segment(self, image_path, *, rendition_id=None, **kw):
        from fichero_server.media.ocr_geometry import OCRGeometryBox, OCRGeometryLevel, OCRGeometryResult

        self.found.append(Path(image_path).name)
        w, h = Image.open(image_path).size
        boxes = []
        for i, y in enumerate((0.3, 0.6)):
            poly = [[0.1 * w, y * h], [0.9 * w, y * h], [0.9 * w, (y + 0.1) * h], [0.1 * w, (y + 0.1) * h]]
            boxes.append(OCRGeometryBox(text="", bbox=[0.1, y, 0.8, 0.1], level=OCRGeometryLevel.LINE,
                                        provider="kraken", model="blla", source="kraken-segment",
                                        metadata={"polygon_px": poly,
                                                  "baseline_px": [[0.1 * w, (y + 0.08) * h], [0.9 * w, (y + 0.08) * h]]}))
        return OCRGeometryResult(text="", provider="kraken", model="blla", source="kraken-segment", boxes=boxes)

    async def vision(self, images, prompt, config, **kw):
        self.read_calls += 1
        return json.dumps([f"línea leída {i}" for i in range(len(images))])


@pytest.fixture
def lines(monkeypatch):
    import fichero_server.llm as llm
    from fichero_server.llm import kraken_runtime
    from fichero_server.media import page_split

    stub = Lines()
    monkeypatch.setattr(kraken_runtime, "segment_to_geometry", stub.segment)
    monkeypatch.setattr(llm, "vision", stub.vision)
    monkeypatch.setattr(page_split, "detect_document_outline", lambda path: None)
    return stub


def _readings_of(client, db, doc_id):
    rows = [s for s in db.query(Segment, document_id=doc_id) if s.kind == "line" and not s.deleted_at]
    return [r for s in rows for r in client.get(f"/api/segments/{s.id}/readings").json()["items"]]


def test_source_recipe_start_runs_the_steps__kraken_lines_read_by_a_vision_model(client, db, pages, tmp_path,  # noqa: F811
                                                                                lines):  # noqa: F811
    """source.recipe.start-runs-the-steps: "... reading a line (with a Kraken reader, or Kraken's lines read by a
    vision model: `Read Lines (Kraken lines, vision model)`) ...". The step's own model reads each line Kraken
    found; never a stand-in."""
    _save(client, _recipe(tmp_path, LINES, READ_WITH_GEMINI))
    plan = client.get("/api/recipes/project/start").json()
    (card,) = plan["runs"]
    assert card["steps"] == ["lines", "read"] and card["workflow"] == "Read Lines (Kraken lines, vision model)"
    assert (card["provider_override"], card["model_override"]) == ("openrouter", "google/gemini-3-flash-preview")
    run = _finished(client, _start(client))
    assert run["state"] == "done", run
    assert sorted(lines.found) == ["p0.png", "p1.png"] and lines.read_calls >= 2
    read = _readings_of(client, db, pages[0].id)
    assert {r["content"] for r in read} == {"línea leída 0", "línea leída 1"}


def _spread(path: Path) -> Path:
    """An open notebook: two pale pages with writing-like strokes, and a dark gutter between them."""
    image = Image.new("RGB", (800, 500), (236, 230, 214))
    draw = ImageDraw.Draw(image)
    for x0 in (60, 460):
        for row in range(60, 440, 30):
            draw.line([(x0, row), (x0 + 280, row)], fill=(70, 60, 50), width=2)
    draw.rectangle([392, 0, 408, 500], fill=(25, 22, 20))
    image.save(path, format="PNG")
    return path


def test_source_recipe_start_runs_the_steps__split_pages_then_its_pages_are_read(client, db, tmp_path,
                                                                                engine, lines):  # noqa: F811
    """source.recipe.start-runs-the-steps (`Split Pages`) and source.recipe.done-is-not-redone ("the pages a step
    runs on are worked out when it starts, so pages a split made earlier in the same run are read like any
    others"): the spread is cut at its gutter, and the read step reads the two pages, not the photograph."""
    from fichero_server.models import DocType, FileType
    from fichero_server.workflows.default_workflows import seed_default_workflows

    seed_default_workflows(db)
    photo = Document(name="spread.png", doc_type=DocType.file, file_type=FileType.image,
                     path=str(_spread(tmp_path / "spread.png")))
    db.save(photo)
    _save(client, _recipe(tmp_path, SPLIT, LINES, KRAKEN_READ))
    run = _finished(client, _start(client))
    assert run["state"] == "done", run
    assert [s["steps"] for s in run["steps"]] == [["split"], ["lines", "read"]]
    children = [d for d in db.query(Document, parent_id=photo.id) if not d.deleted_at]
    assert len(children) == 2, "the spread is cut into its two pages"
    assert len(engine.read) == 2 and "spread.png" not in engine.read, "the pages are read, not the photograph"


def test_source_recipe_done_is_not_redone(client, db, pages, tmp_path, lines):  # noqa: F811
    """source.recipe.done-is-not-redone: "a started recipe does not run a step again on a page that already has its
    output ... The Start plan says, for each such step, "already done on N of M pages", and the run does only the
    rest, unless the person names the steps to redo when pressing Start. A step that cannot tell (names,
    statements, checks, export, publish) runs on every page, and the plan says so.\""""
    check = {"id": "check", "job": "check", "settings": {"layer": "claims"}, "model": GEMINI,
             "runs_on": "cloud:openrouter"}
    _save(client, _recipe(tmp_path, LINES, READ_WITH_GEMINI, check))
    _finished(client, _start(client))
    first = lines.read_calls

    plan = client.get("/api/recipes/project/start").json()
    read_card, check_card = plan["runs"]
    assert (read_card["done"], read_card["of"]) == (2, 2) and "already done on 2 of 2 pages" in read_card["note"]
    assert check_card["done"] is None and "every page" in check_card["note"]
    again = _finished(client, _start(client))
    assert again["state"] == "done" and lines.read_calls == first, "nothing read twice"

    from fichero_server.models import DocType, FileType
    from tests.unit.recipes.test_recipe_execution_to_spec import _png

    db.save(Document(name="p2.png", doc_type=DocType.file, file_type=FileType.image, path=str(_png(tmp_path / "p2.png"))))
    read_card = client.get("/api/recipes/project/start").json()["runs"][0]
    assert (read_card["done"], read_card["of"]) == (2, 3)
    lines.found = []
    _finished(client, _start(client))
    assert lines.found == ["p2.png"], "only the page not yet read"

    other = {**READ_WITH_GEMINI, "model": {"cloud": "openrouter", "model": "qwen/qwen3-vl-8b"}}
    _save(client, _recipe(tmp_path, LINES, other, check))
    read_card = client.get("/api/recipes/project/start").json()["runs"][0]
    assert (read_card["done"], read_card["of"]) == (0, 3), "a page read by another model is not read by this one"
    _save(client, _recipe(tmp_path, LINES, READ_WITH_GEMINI, check))

    lines.found = []
    r = client.post("/api/recipes/project/start", json={"redo": ["read"]})
    assert r.status_code == 200, r.text
    _finished(client, r.json()["started"]["job_id"])
    assert sorted(lines.found) == ["p0.png", "p1.png", "p2.png"], "redo runs the step on every page"


READ_PAGE = {"id": "read", "job": "read-a-page", "model": GEMINI, "runs_on": "cloud:openrouter"}


def test_source_chain_checked_before_run__a_page_reading_meets_the_names_step(client, db, pages, tmp_path,  # noqa: F811
                                                                            monkeypatch, lines):  # noqa: F811
    """source.chain.checked-before-run: "finding names, finding statements, checking and exporting take readings of
    the lines **or** a reading of the whole page, so a recipe that reads whole pages passes; one that gives neither
    is refused, naming both." Also source.recipe.done-is-not-redone for reading a page: a page already read by the
    step's own model is not read again."""
    names = {"id": "names", "job": "find-names-tag-words"}
    check = {"id": "check", "job": "check", "settings": {"layer": "claims"}, "model": GEMINI,
             "runs_on": "cloud:openrouter"}
    _save(client, _recipe(tmp_path, READ_PAGE, names, check))
    plan = client.get("/api/recipes/project/start").json()
    assert plan["refusals"] == [], plan["refusals"]

    _save(client, _recipe(tmp_path, names))
    (refusal,) = client.get("/api/recipes/project/start").json()["refusals"]
    assert "line_readings or page_reading" in refusal, refusal

    import fichero_server.llm as llm

    reads = []

    async def read_a_page(images, prompt, config, **kw):
        reads.append(config.model)
        return "Sepan quantos esta carta vieren"

    monkeypatch.setattr(llm, "vision", read_a_page)
    _save(client, _recipe(tmp_path, READ_PAGE))
    run = _finished(client, _start(client))
    assert run["state"] == "done", run
    read_card = client.get("/api/recipes/project/start").json()["runs"][0]
    assert (read_card["done"], read_card["of"]) == (2, 2), read_card
    assert reads and set(reads) == {"google/gemini-3-flash-preview"}
    first = len(reads)
    _finished(client, _start(client))
    assert len(reads) == first, "a page already read by this model is not read again"
    other = {**READ_PAGE, "model": {"cloud": "openrouter", "model": "qwen/qwen3-vl-8b"}}
    _save(client, _recipe(tmp_path, other))
    read_card = client.get("/api/recipes/project/start").json()["runs"][0]
    assert (read_card["done"], read_card["of"]) == (0, 2), "a page read by another model is not read by this one"


TIE = {"id": "tie", "job": "tie-text-to-lines", "model": {"zenodo": "10.5281/zenodo.13788177"}}


def test_source_job_tie_text_to_lines__a_recipe_card_runs_it(client, db, pages, tmp_path, monkeypatch,  # noqa: F811
                                                              lines):  # noqa: F811
    """source.job.tie-text-to-lines (#5444: "the job has no card"): a recipe step that ties the page reading to
    its lines runs, after Start, as the tie job with the step's Kraken reader, on this Mac; each line of the
    page's own pass gets its stretch of the page reading as a reading.
    WHY: Kraken's lines and a cloud model's page text are only a training set once a recipe ties them."""
    import fichero_server.llm as llm
    from fichero_server.api.routes.document.segment_readings import counting_texts, ordered_lines
    from fichero_server.execution import jobs
    from fichero_server.llm import kraken_runtime
    from fichero_server.models.segments import SegmentPass

    async def read_a_page(images, prompt, config, **kw):
        return "Yten dixo el testigo\nque lo vio"

    monkeypatch.setattr(llm, "vision", read_a_page)
    monkeypatch.setattr(kraken_runtime, "read_given_lines",
                        lambda image_path, model_path, found, **kw: ["yten dixo el testigo", "que lo vio"])
    _save(client, _recipe(tmp_path, LINES, READ_PAGE, TIE))
    plan = client.get("/api/recipes/project/start").json()
    assert plan["refusals"] == [], plan["refusals"]
    tie = next(r for r in plan["runs"] if r["steps"] == ["tie"])
    assert (tie["card"], tie["check"], tie["provider"], tie["model"]) == (
        "check", "tie-text-to-lines", "kraken", "kraken-mccatmus")
    run = _finished(client, _start(client))
    assert run["state"] == "done", run
    step = next(s for s in run["steps"] if s["steps"] == ["tie"])
    assert jobs.read_job(db, step["child_id"])["kind"] == "tie-text-to-lines"
    for page in pages:
        (pass_row,) = [p for p in db.query(SegmentPass, document_id=page.id) if not p.deleted_at]
        rows = ordered_lines(db, pass_row.id)
        texts = counting_texts(db, rows)
        assert [texts.get(r.id) for r in rows] == ["Yten dixo el testigo", "que lo vio"]
