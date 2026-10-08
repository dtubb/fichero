"""Each page read by the reader for its kind (#5578), tested to the spec
(docs/contributor_manual/specs/source/models-chains-and-projects.md, section 7b, "Everything automatic after Start").

Behaviour: `source.onboard.auto.reader-per-material`. Through the public surface: `PUT /api/recipes/project`,
`GET|POST /api/recipes/project/start`, the recipe run's status route, the document update route (a person's
correction of a page's kind) and the real job scheduler. The readers are the recipe execution tests' stub Kraken
reader at the Kraken runtime, which records which model read which page.
"""
from __future__ import annotations

import math
import random
from pathlib import Path

from PIL import Image, ImageDraw

from fichero_server.recipes import sorting
from tests.unit.recipes.test_recipe_execution_to_spec import (  # noqa: F401  (fixtures)
    _finished,
    _recipe,
    _start,
    engine,
)

HAND = "10.5281/zenodo.13788177"
TYPE = "10.5281/zenodo.10519596"
LINES = {"id": "lines", "job": "find-lines", "model": {"kraken": "blla", "kraken_version": "bundled"}}


def _typed(path: Path, *, blank: bool = False) -> Path:
    """Machine text: words on straight lines with clean gaps between them (a blank verso: faint bleed-through)."""
    image = Image.new("L", (240, 320), 232)
    draw = ImageDraw.Draw(image)
    rng = random.Random(path.name)
    for row in range(24, 300, 12):
        x = 16
        while x < 220:
            width = rng.randint(6, 22)
            draw.rectangle([x, row, x + width, row + 4], fill=205 if blank else 40)
            x += width + rng.randint(4, 9)
        if blank and row > 120:
            break
    image.save(path)
    return path


def _handwritten(path: Path) -> Path:
    """Handwriting: wavering strokes on drifting lines whose loops fill the space between them."""
    image = Image.new("L", (240, 320), 232)
    draw = ImageDraw.Draw(image)
    rng = random.Random(path.name)
    for base in range(24, 300, 14):
        drift = rng.uniform(-0.04, 0.04)
        points = [(x, base + drift * x + 7 * math.sin(x / rng.uniform(2.5, 4.0))) for x in range(16, 224, 2)]
        draw.line(points, fill=40, width=2)
    image.save(path)
    return path


def test_the_heuristic_tells_machine_text_from_handwriting(tmp_path):
    assert sorting._machine_made(str(_typed(tmp_path / "typed.png"))) is True
    assert sorting._machine_made(str(_handwritten(tmp_path / "hand.png"))) is False
    assert sorting._machine_made(str(tmp_path / "missing.png")) is None


def _folder(db, tmp_path):
    """A box of four photographs: a typed page, its blank back, a handwritten page, and a handwritten-looking page
    a person will say is typescript."""
    from fichero_server.models import DocType, Document, FileType
    from fichero_server.workflows.default_workflows import seed_default_workflows

    seed_default_workflows(db)
    folder = Document(name="Box 1", doc_type=DocType.folder)
    db.save(folder)
    drawn = [_typed(tmp_path / "typed.png"), _typed(tmp_path / "typed-back.png", blank=True),
             _handwritten(tmp_path / "hand.png"), _handwritten(tmp_path / "corrected.png")]
    ids = {}
    for i, path in enumerate(drawn):
        doc = Document(name=path.name, doc_type=DocType.file, file_type=FileType.image, path=str(path),
                       parent_id=folder.id, sort_order=i)
        db.save(doc)
        ids[path.stem] = doc.id
    return ids


def _read_step(stays_local_reader: dict | None = None) -> dict:
    readers = [{"material": "handwriting", "model": {"zenodo": HAND}, "runs_on": "this-mac"},
               {"material": "typescript", "model": {"zenodo": TYPE}, "runs_on": "this-mac"}]
    if stays_local_reader:
        readers.append(stays_local_reader)
    return {"id": "read", "job": "read-a-line", "model": {"zenodo": HAND}, "material": "handwriting",
            "readers": readers}


def test_source_onboard_auto_reader_per_material(client, db, tmp_path, engine, monkeypatch):
    """source.onboard.auto.reader-per-material: "each page is read by the reader for its kind. A cheap first job
    sorts the pages (handwriting, print, typescript, blank) from the image, and a person's correction of a page's
    kind is kept.\""""
    from fichero_server.llm import kraken_runtime

    read_by: dict[str, str] = {}
    recognize = engine.recognize

    def resolve(ref):
        return f"/models/{ref}.mlmodel", ref

    def recognize_and_note(image_path, model_path, **kw):
        read_by[Path(image_path).name] = Path(model_path).stem
        return recognize(image_path, model_path, **kw)

    def read_given_lines(image_path, model_path, lines, **kw):
        """A page whose lines were found already is read on them (a second run)."""
        read_by[Path(image_path).name] = Path(model_path).stem
        return ["Yten dixo el testigo" for _ in lines]

    monkeypatch.setattr(kraken_runtime, "resolve_recognition_model", resolve)
    monkeypatch.setattr(kraken_runtime, "recognize_to_geometry", recognize_and_note)
    monkeypatch.setattr(kraken_runtime, "read_given_lines", read_given_lines)
    ids = _folder(db, tmp_path)

    # A person says the last page is typescript, through the document update route.
    r = client.put(f"/api/documents/{ids['corrected']}", json={"attributes": {"material": "typescript"}})
    assert r.status_code == 200, r.text
    assert r.json()["attributes"] == {"material": "typescript", "material_set_by": "person"}

    cloud_print = {"material": "print", "model": {"cloud": "openai", "model": "gpt-5"}, "runs_on": "cloud:openai"}
    recipe = _recipe(tmp_path, LINES, _read_step(cloud_print))
    r = client.put("/api/recipes/project", json={"answers": {"purpose": "transcribe", "cloud_allowed": False},
                                                 "recipe": recipe})
    assert r.status_code == 200, r.text
    plan = client.get("/api/recipes/project/start").json()
    assert plan["refusals"] == [], plan
    (card,) = [c for c in plan["runs"] if c["job"] == "read-a-line"]
    # The plan carries one reader per kind; a reader that would send pages off this Mac is not among them.
    assert set(card["readers"]) == {"handwriting", "typescript"}
    hand_model = card["readers"]["handwriting"]["model_override"]
    type_model = card["readers"]["typescript"]["model_override"]
    assert hand_model != type_model and card["model_override"] == hand_model

    run = _finished(client, _start(client))
    assert run["state"] == "done", run
    # The blank back is not read; the typed page (no print reader here: machine text is typescript) by the
    # typescript reader; the handwritten page by the handwriting reader; the person's typescript page by the
    # typescript reader although it looks handwritten.
    assert read_by == {"typed.png": type_model, "hand.png": hand_model, "corrected.png": type_model}
    (step,) = run["steps"]
    assert step["blank_versos"] == 1 and step["kinds"] == {"handwriting": 1, "typescript": 2}
    assert sorted((r["material"], r["pages"], r["model"], r["state"]) for r in step["readers"]) == [
        ("handwriting", 1, hand_model, "done"), ("typescript", 2, type_model, "done")]

    def attrs(key):
        return client.get(f"/api/documents/{ids[key]}").json()["attributes"]

    assert attrs("typed") == {"material": "typescript", "material_set_by": "sorting"}
    assert attrs("typed-back") == {"material": "blank", "material_set_by": "sorting"}
    assert attrs("hand") == {"material": "handwriting", "material_set_by": "sorting"}
    assert attrs("corrected") == {"material": "typescript", "material_set_by": "person"}

    # A person's correction of a sorted page is kept: the next run reads it with the reader for its new kind.
    r = client.put(f"/api/documents/{ids['hand']}", json={"attributes": {"material": "typescript"}})
    assert r.status_code == 200 and r.json()["attributes"]["material_set_by"] == "person"
    read_by.clear()
    r = client.post("/api/recipes/project/start", json={"redo": ["read"]})
    assert r.status_code == 200, r.text
    again = _finished(client, r.json()["started"]["job_id"])
    assert again["state"] == "done", again
    assert read_by == {"typed.png": type_model, "hand.png": type_model, "corrected.png": type_model}
    assert attrs("hand") == {"material": "typescript", "material_set_by": "person"}


def test_one_reader_sorts_only_the_blank_pages(client, db, tmp_path, engine):
    """A step with one reader reads every page but the blank ones with it (the back of a leaf, and a page a person
    called blank): nothing else is sorted or written."""
    ids = _folder(db, tmp_path)
    r = client.put(f"/api/documents/{ids['corrected']}", json={"attributes": {"material": "blank"}})
    assert r.status_code == 200, r.text
    recipe = _recipe(tmp_path, LINES, {"id": "read", "job": "read-a-line", "model": {"zenodo": HAND}})
    r = client.put("/api/recipes/project", json={"answers": {"purpose": "transcribe"}, "recipe": recipe})
    assert r.status_code == 200, r.text
    (card,) = [c for c in client.get("/api/recipes/project/start").json()["runs"] if c["job"] == "read-a-line"]
    assert card["readers"] is None
    run = _finished(client, _start(client))
    assert run["state"] == "done", run
    assert sorted(engine.read) == ["hand.png", "typed.png"] and run["steps"][0]["blank_versos"] == 2
    assert client.get(f"/api/documents/{ids['typed']}").json()["attributes"] == {}
    assert client.get(f"/api/documents/{ids['typed-back']}").json()["attributes"]["material"] == "blank"
