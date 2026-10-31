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
    assert not made.is_primary and made.transform is None
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
