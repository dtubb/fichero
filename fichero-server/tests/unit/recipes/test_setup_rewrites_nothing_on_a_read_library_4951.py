"""`source.onboard.existing-library` (#4951): setup on a library already read rewrites nothing: saving new answers
and a new recipe leaves every page, segment and reading as it was. Only Start runs anything.

WHY: a person re-running setup on a library with years of corrected readings must not lose or touch one of them.
"""
from __future__ import annotations

from fichero_server.models import ContentRepresentation, Document
from fichero_server.models.segments import Segment
from tests.unit.api.test_add_a_layer_later import (  # noqa: F401  (fixtures)
    _kraken_readers_on_this_mac,
    hold_the_run,
    project,
)
from tests.unit.recipes.test_unread_lines_not_read_5758 import _page


def _everything(db):
    return {kind.__name__: sorted((row.id, row.model_dump_json()) for row in db.all(kind))
            for kind in (Document, Segment, ContentRepresentation)}


def test_saving_setup_again_leaves_every_page_segment_and_reading_as_it_was(client, db, project):  # noqa: F811
    _page(db, lines=3, read=2)  # a page already lined and read
    before = _everything(db)
    assert before["ContentRepresentation"] and before["Segment"]

    answers = {"purpose": "transcribe", "languages": ["es", "la"], "scripts": ["Latn"], "material": "handwriting",
               "mac_memory_gb": 16}
    recipe = client.post("/api/recipes/assemble", json=answers).json()
    r = client.put("/api/recipes/project", json={"answers": answers, "recipe": recipe})
    assert r.status_code == 200, r.text

    assert _everything(db) == before


def test_swapping_a_steps_model_in_the_recipe_rewrites_no_existing_reading(client, db, project):  # noqa: F811
    """`source.onboard.rerun-rewrites-nothing`: a new model is a default for new work; the readings made by the old one
    stay as they were, and the swap is what the saved recipe now says."""
    _page(db, lines=3, read=2)
    answers = {"purpose": "transcribe", "languages": ["es"], "scripts": ["Latn"], "material": "handwriting",
               "mac_memory_gb": 16}
    recipe = client.post("/api/recipes/assemble", json=answers).json()
    assert client.put("/api/recipes/project", json={"answers": answers, "recipe": recipe}).status_code == 200
    before = _everything(db)

    step = next(s for s in recipe["steps"] if s.get("model"))
    swapped = {"zenodo": "10.5281/zenodo.99"}
    assert step["model"] != swapped
    step["model"] = swapped
    r = client.put("/api/recipes/project", json={"answers": answers, "recipe": recipe})
    assert r.status_code == 200, r.text

    assert _everything(db) == before
    saved = client.get("/api/recipes/project").json()["recipe"]
    assert next(s for s in saved["steps"] if s["id"] == step["id"])["model"] == swapped
