"""#6245: a project deleted (or its Set Up cancelled) before Start never leaves the person's files moved.

WHY: the owner (2026-10-28) found a new project's Set Up moved the files added in Add Material at once; deleting the
project before Start sent those files to the Trash with it. While Set Up chose Move and Start has not been pressed,
an import copies and leaves the source where it is; Start finishes the move.
"""
from __future__ import annotations

from pathlib import Path

from fichero_server.importers.ingest import IngestMode, ingest_file
from fichero_server.models import Document
from tests.unit.recipes.test_bakeoff_readers import folder  # noqa: F401
from tests.unit.recipes.test_recipe_execution_to_spec import engine, pages  # noqa: F401

ANSWERS = {"purposes": ["transcribe"], "languages": ["es"], "scripts": ["Latn"], "materials": ["handwriting"],
           "pages": 1000, "mac_memory_gb": 32}


def _set_up_with_move(client):
    recipe = client.post("/api/recipes/assemble", json=ANSWERS)
    assert recipe.status_code == 200, recipe.text
    saved = client.put("/api/recipes/project", json={"answers": {**ANSWERS, "ingest_mode": "move"}, "recipe": recipe.json()})
    assert saved.status_code == 200, saved.text


def _move_in(db, tmp_path) -> tuple[Path, Document]:
    source = tmp_path / "outside" / "letter.txt"
    source.parent.mkdir()
    source.write_text("the person's only copy", encoding="utf-8")
    doc = ingest_file(source, mode=IngestMode.MOVE, db=db, package_path=Path(db.path).parent, auto_embed=False)
    return source, doc


def test_a_move_during_set_up_leaves_the_file_where_it_was(client, db, folder, pages, engine, tmp_path):  # noqa: F811
    _set_up_with_move(client)
    source, doc = _move_in(db, tmp_path)
    assert source.read_text(encoding="utf-8") == "the person's only copy"
    assert db.get(Document, doc.id).metadata.get("move_pending") is True


def test_start_finishes_the_moves_set_up_held(client, db, folder, pages, engine, tmp_path):  # noqa: F811
    _set_up_with_move(client)
    source, doc = _move_in(db, tmp_path)
    pressed = client.post("/api/recipes/project/start", json={})
    assert pressed.status_code == 200, pressed.text
    assert not source.exists()
    kept = db.get(Document, doc.id)
    assert "move_pending" not in kept.metadata
    stored = Path(kept.path) if Path(kept.path).is_absolute() else Path(db.path).parent / kept.path
    assert stored.read_text(encoding="utf-8") == "the person's only copy"


def test_a_move_after_start_moves_at_once(client, db, folder, pages, engine, tmp_path):  # noqa: F811
    _set_up_with_move(client)
    assert client.post("/api/recipes/project/start", json={}).status_code == 200
    source, _ = _move_in(db, tmp_path)
    assert not source.exists()
