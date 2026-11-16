"""Faded pages prepared as a recipe step (#5580), tested to the spec
(docs/contributor_manual/specs/source/models-chains-and-projects.md, section 7b, "Everything automatic after Start",
`source.onboard.auto.prepare-damaged-images`).

Through the public surface: `POST /api/recipes/assemble` (with and without the open project's sample),
`PUT /api/recipes/project`, `GET|POST /api/recipes/project/start`, the recipe run's status and the real job scheduler.
The Kraken reader is the stub the recipe execution tests use, at the Kraken runtime: it records which picture it read.
"""
# ruff: noqa: F811  (fixtures imported from the execution tests are re-taken as arguments: pytest's idiom)
from __future__ import annotations

import hashlib
from pathlib import Path

from fichero_server.models import Rendition
from fichero_server.recipes import prepare
from fichero_server.recipes.jobs import get_job
from tests.unit.recipes.test_recipe_execution_to_spec import (  # noqa: F401  (fixtures)
    _finished,
    _recipe,
    _start,
    engine,
    pages,
)

PREP = {"id": "prep", "job": "prepare-the-image", "model": {"builtin": "image-preparer"}}
LINES = {"id": "lines", "job": "find-lines", "model": {"kraken": "blla", "kraken_version": "bundled"}}
READ = {"id": "read", "job": "read-a-line", "model": {"zenodo": "10.5281/zenodo.13788177"}}


def _page(path: Path, *, paper: int, ink: int) -> Path:
    """A page: paper with a block of written lines in `ink`."""
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (200, 260), (paper, paper, paper - 10))
    draw = ImageDraw.Draw(image)
    for y in range(30, 230, 20):
        for x in range(20, 180, 24):  # words, not a ruled line: a full-width bar is ruling, and a page of only ruling is blank
            draw.rectangle([x, y, x + 14, y + 6], fill=(ink, ink, ink))
    image.save(str(path), format="PNG")
    return path


def _assemble(client, **answers):
    body = {"languages": ["es"], "scripts": ["Latn"], "mac_memory_gb": 16, **answers}
    r = client.post("/api/recipes/assemble", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def _save(client, recipe):
    r = client.put("/api/recipes/project", json={"answers": {"purposes": ["transcribe"]}, "recipe": recipe})
    assert r.status_code == 200, r.text


def _faded_and_clear(db, pages, tmp_path):
    """The first page faded (grey ink on yellowed paper), the second clear (black ink on white)."""
    faded, clear = pages
    faded.path = str(_page(tmp_path / "faded.png", paper=215, ink=160))
    clear.path = str(_page(tmp_path / "clear.png", paper=245, ink=20))
    db.save(faded)
    db.save(clear)
    return faded, clear


def _digest(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def test_faded_is_measured_and_a_blank_page_is_not_faded(tmp_path):
    """"where the sample shows faded [...] pages": the measure, a page's grey spread, tells faded ink from clear ink;
    a blank page has nothing to raise."""
    assert prepare.is_faded(str(_page(tmp_path / "f.png", paper=215, ink=160)))
    assert not prepare.is_faded(str(_page(tmp_path / "c.png", paper=245, ink=20)))
    assert not prepare.is_faded(str(_page(tmp_path / "b.png", paper=240, ink=240)))
    assert not prepare.is_faded(None) and not prepare.is_faded(str(tmp_path / "missing.png"))


def test_faded_pages_add_the_step_before_lines(client, with_material):
    """"image preparation (contrast, deskew) is proposed as a step [...]. It runs before lines": the step has no model
    to choose (Fichero's own), runs on this Mac, and comes after splitting and before lines."""
    plain = _assemble(client, purposes=["transcribe"], faded_pages=False)
    assert "prepare-the-image" not in [s["job"] for s in plain["steps"]]
    assert "prepare-the-image" not in [b["job"] for b in plain["by_hand"]]
    faded = _assemble(client, purposes=["transcribe"], faded_pages=True, jobs=["split-pages"])
    order = [s["job"] for s in faded["steps"]]
    assert order.index("split-pages") < order.index("prepare-the-image") < order.index("find-lines")
    (step,) = [s for s in faded["steps"] if s["job"] == "prepare-the-image"]
    assert step["model"] == {"builtin": "image-preparer"} and step["runs_on"] == "this-mac"
    assert step["gap"] is None and faded["problems"] == [] and "faded" in step["reasons"][0]
    # Nothing that lines or reads the pages: nothing to prepare them for.
    assert "prepare-the-image" not in [s["job"] for s in _assemble(client, faded_pages=True)["steps"]]


def test_on_when_the_projects_sample_shows_a_faded_page(client, db, pages, tmp_path):
    """"where the sample shows faded or damaged pages": unset, the answer is measured on the open project's sample."""
    assert "prepare-the-image" not in [s["job"] for s in _assemble(client, purposes=["transcribe"])["steps"]]
    _faded_and_clear(db, pages, tmp_path)
    assert "prepare-the-image" in [s["job"] for s in _assemble(client, purposes=["transcribe"])["steps"]]
    off = _assemble(client, purposes=["transcribe"], faded_pages=False)
    assert "prepare-the-image" not in [s["job"] for s in off["steps"]]


def test_the_step_is_a_card_start_runs_before_lines(client, tmp_path):
    """"[...] proposed as a step with a card": Start runs it as its own card (`prepare`), first."""
    _save(client, _recipe(tmp_path, PREP, LINES, READ))
    r = client.get("/api/recipes/project/start")
    assert r.status_code == 200, r.text
    plan = r.json()
    assert [r["card"] for r in plan["runs"]] == ["prepare", "workflow"]
    card = plan["runs"][0]
    assert card["steps"] == ["prep"] and card["job"] == "prepare-the-image"
    assert set(card["gives"]) == set(get_job("prepare-the-image").gives)
    assert "prep" not in {s["step"] for s in plan["skipped"]}


def test_start_prepares_the_faded_page_and_lines_read_the_prepared_copy(client, db, pages, tmp_path, engine):
    """"It runs before lines, and the original image is kept": the faded page gets a new rendition, its contrast
    raised, in the page's own frame; the clear page is left alone; lines and reading read the prepared copy of the
    faded page and the original of the clear one; the original file is untouched. Run again, neither page is looked
    at twice (#5706)."""
    faded, clear = _faded_and_clear(db, pages, tmp_path)
    before = _digest(faded.path)
    _save(client, _recipe(tmp_path, PREP, LINES, READ))
    run = _finished(client, _start(client))
    assert run["state"] == "done", run
    prep, read = run["steps"]
    assert prep["steps"] == ["prep"] and prep["state"] == "done"
    assert prep["prepared"] == {"prepared": 1, "clear": 1, "no_image": 0}
    assert read["state"] == "done"

    (made,) = [r for r in db.query(Rendition, document_id=faded.id) if r.role == "prepared"]
    assert not made.is_primary and made.transform.rect == [0.0, 0.0, 1.0, 1.0]  # the page's own frame, said (wide.faded.*)
    library = Path(db.path).parent
    stored = library / made.path
    assert stored.is_file() and not Path(made.path).is_absolute()
    from PIL import Image

    with Image.open(stored) as image, Image.open(faded.path) as original:
        assert image.size == original.size == (made.pixel_width, made.pixel_height)
    assert prepare.contrast_spread(str(stored)) >= prepare.FADED_BELOW  # the faded ink raised
    assert _digest(faded.path) == before  # the original is kept
    assert [r for r in db.query(Rendition, document_id=clear.id) if r.role == "prepared"] == []
    assert sorted(engine.read) == sorted([stored.name, "clear.png"])  # lines and reading read the prepared copy

    again = _finished(client, _start(client))
    assert again["state"] == "done", again
    # Neither page is looked at again: the faded one is prepared, and the clear one was looked at and found clear
    # (#5706: the plan said "already done on 4 of 92" after a run that found 88 clear).
    assert again["steps"][0].get("prepared") is None and again["steps"][0]["state"] == "done", again["steps"][0]
    assert len([r for r in db.query(Rendition, document_id=faded.id) if r.role == "prepared"]) == 1


def _unfound_page(db, tmp_path, monkeypatch, name="scan.png"):
    from fichero_server.media import find_page as module
    from fichero_server.media import turn_by_text as turn_module
    from fichero_server.models import DocType, Document, FileType

    monkeypatch.setattr(module, "find_page", lambda image: None)
    monkeypatch.setattr(turn_module, "read_lines", lambda image, db_path=None: [(0.04, 0.07 + 0.13 * i, 0.45, 0.07) for i in range(6)])
    path = _page(tmp_path / name, paper=240, ink=30)
    doc = Document(name=path.name, doc_type=DocType.file, file_type=FileType.image, path=str(path), metadata={})
    db.save(doc)
    return doc


def test_wide_the_stamp_follows_only_the_page_operations_never_the_paper_answer_or_clarity(db, tmp_path, monkeypatch):
    """`wide.prepare.rerun-follows-the-answers` (#5706, section F cause 2; review H1): a page's preparation is stamped with the page
    operations that made it (crop, straighten) and nothing else. Ticking faded or switching Clarity changes neither, so the page is
    `unchanged`, its renditions are not rewritten and its image signature stays (a new signature makes Read read the page again)."""
    from fichero_server.media.current_image import current_page_image
    from fichero_server.recipes.prepare_run import run_prepare

    doc = _unfound_page(db, tmp_path, monkeypatch)
    first: dict = {}
    run_prepare(db, [doc.id], "run-1", first, paper=[], operations=["crop", "straighten"])
    assert first["page_prep"]["pages"] == 1 and first["page_prep"]["unchanged"] == 0
    signature = current_page_image(db, db.get(type(doc), doc.id)).signature
    # "ruled" is no longer in this loop: it now runs ruled-lines into an enhanced rendition, which is a different image (test_start_plan_prepare_step.py).
    for paper, ops in ((["faded"], ["crop", "straighten", "clarity"]), (["unknown-answer"], ["crop", "straighten"])):
        again: dict = {}
        run_prepare(db, [doc.id], "run-2", again, paper=paper, operations=ops)
        assert again["page_prep"]["unchanged"] == 1 and again["page_prep"]["pages"] == 0, (paper, ops)
        assert current_page_image(db, db.get(type(doc), doc.id)).signature == signature, "the image is the same one"
    fewer: dict = {}
    run_prepare(db, [doc.id], "run-3", fewer, paper=[], operations=["crop"])
    assert fewer["page_prep"]["pages"] == 1, "a page operation switched off changes what the page comes out as: prepared again"


def test_wide_a_stamp_from_before_the_operations_holds_for_a_cut_page_and_not_for_an_unfound_one(db, tmp_path, monkeypatch):
    """Review H1: an earlier build's stamp (no operations) stays valid where this build would produce the same page, a page it cut,
    and is stale only for a page it left whole, which this build now turns and straightens."""
    from fichero_server.recipes import page_crop

    legacy = lambda path: {**page_crop._stamp(path, None), "version": 2}  # noqa: E731 -- the stamp as version 2 wrote it
    legacy_stamp = lambda path: {k: v for k, v in legacy(path).items() if k != "operations"}  # noqa: E731
    whole = _unfound_page(db, tmp_path, monkeypatch)
    cut = _unfound_page(db, tmp_path, monkeypatch, name="cut.png")
    for doc, box in ((whole, None), (cut, [0.1, 0.1, 0.8, 0.8])):
        meta = {"page_prep_stamp": legacy_stamp(Path(doc.path)), **({"page_box": box} if box else {})}
        db.save(doc.model_copy(update={"metadata": meta}))
    got = page_crop.crop_pages(db, [whole.id, cut.id], "run-1", prepare=True, reuse=True,
                               signature={"operations": ["crop", "straighten"]})
    assert got["unchanged"] == 1 and got["pages"] == 1, got


def test_wide_the_stamp_keeps_a_changed_file_and_the_rules_version_apart(db, tmp_path, monkeypatch):
    """The stamp still names the file and the rules: another file is prepared again whatever the answers."""
    from fichero_server.recipes.page_crop import crop_pages

    doc = _unfound_page(db, tmp_path, monkeypatch)
    crop_pages(db, [doc.id], "run-1", prepare=True, reuse=True, signature={"operations": ["crop", "straighten"]})
    assert crop_pages(db, [doc.id], "run-2", prepare=True, reuse=True, signature={"operations": ["crop", "straighten"]})["unchanged"] == 1
    _page(Path(doc.path), paper=200, ink=60)  # the file changes
    assert crop_pages(db, [doc.id], "run-3", prepare=True, reuse=True, signature={"operations": ["crop", "straighten"]})["pages"] == 1
