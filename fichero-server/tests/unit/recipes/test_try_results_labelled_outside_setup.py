"""`wide.try.shown-outside-set-up` (#5806): a kept try's readings are listed for the page it ran on, labelled as a try's with its day and
model, on the project's matching lines; nothing is written and the done rule never counts them."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from fichero_server.db.manager import db_manager
from fichero_server.models import ContentRepresentation
from fichero_server.recipes import adopt, done, samples
from tests.unit.recipes.test_adopt_a_pages_readings_6127 import _tried
from tests.unit.training.test_kraken_training_set import notebook  # noqa: F401  (the fixture)


@pytest.fixture
def kept(db, tmp_path, notebook):  # noqa: F811
    """A project page and its kept try on stage `read`, the copy living where `adopt.kept_copies` looks."""
    library = Path(db.path).parent
    scratch = samples._folder(library) / "read.fichero"
    for sub in ("lance", "storage", "files"):
        (scratch / sub).mkdir(parents=True)
    copy_db = db_manager.get_database(scratch)
    page, rec, before = _tried(db, copy_db, tmp_path, notebook)
    adopt.keep(scratch, {"stage": "read", "pages": [rec]})
    samples._result_path(library, "read").write_text(json.dumps({"adoption": {"stage": "read", "before": before, "pages": [rec]}}))
    db_manager.close_database(scratch)
    return page


def test_a_page_lists_the_try_that_ran_on_it_labelled_as_a_try(db, kept):
    (one,) = adopt.tries_on_page(db, kept.id)
    assert one["kind"] == "try" and one["stage"] == "read" and one["model"] == "m" and one["ran_at"]
    assert [r["text"] for r in one["readings"]] == ["hola"]


def test_a_page_the_try_did_not_run_on_lists_nothing(db, kept):
    assert adopt.tries_on_page(db, "no-such-page") == []


def test_listing_writes_nothing_and_the_page_does_not_count_as_read(db, kept):
    adopt.tries_on_page(db, kept.id)
    assert not [r for r in db.query(ContentRepresentation, document_id=kept.id) if r.content == "hola"]
    assert not done._has_line_readings(db, kept.id, "m")


def test_the_route_answers_the_same(client, db, kept):
    body = client.get(f"/api/recipes/tries/page/{kept.id}").json()
    assert body["tries"][0]["kind"] == "try" and body["tries"][0]["readings"][0]["text"] == "hola"
