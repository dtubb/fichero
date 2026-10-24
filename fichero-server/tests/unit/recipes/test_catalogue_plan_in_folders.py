"""The Start plan says what Catalogue will do in folders (the new or changed folder and its parents; the rest already
described), prices those folders, and the run redoes exactly them (`source.recipe.catalogue-follows-new-material`)."""
from __future__ import annotations

from fichero_server.recipes import catalogue_step
from fichero_server.recipes.done import annotate

from tests.unit.recipes.test_catalogue_stage_6087 import CONFIG, DocType, _node, _tree, asked  # noqa: F401

CARD = {"job": "describe-for-the-catalogue", "steps": ["describe-for-the-catalogue"]}


def _plan(db):
    plan = {"runs": [dict(CARD)]}
    return annotate(db, plan)["runs"][0]


def test_the_plan_counts_folders_not_pages(db, asked):  # noqa: F811
    top, box, pages = _tree(db)
    card = _plan(db)
    assert card["note"] == "describes 2 folders; 0 already described" and (card["done"], card["of"]) == (0, 2)
    catalogue_step.describe_folders(db, pages, CONFIG, run_id=None)
    assert _plan(db)["note"] == "already described on all 2 folders; nothing to run"


def test_a_new_folder_plans_itself_and_its_parents_only(db, asked):  # noqa: F811
    top, box, pages = _tree(db)
    other = _node(db, "Box 0", DocType.folder, top)
    old = [_node(db, "q", DocType.page, other, "Old letter")]
    catalogue_step.describe_folders(db, pages + old, CONFIG, run_id=None)
    fresh = _node(db, "Box 2", DocType.folder, top)
    _node(db, "n0", DocType.page, fresh, "New letter")
    assert _plan(db)["note"] == "describes 2 folders; 2 already described"  # Box 2 and Top; Box 0 and Box 1 stay


def test_a_page_read_again_replans_its_folder_and_the_ones_above(db, asked):  # noqa: F811
    top, box, pages = _tree(db)
    other = _node(db, "Box 0", DocType.folder, top)
    old = [_node(db, "q", DocType.page, other, "Old letter")]
    catalogue_step.describe_folders(db, pages + old, CONFIG, run_id=None)
    from fichero_server.models import Document

    page = db.get(Document, pages[0])
    page.page_content = "Letter 0, read again by another reader"
    db.save(page)
    assert _plan(db)["note"] == "describes 2 folders; 1 already described"  # Box 1 and Top; Box 0 stays
    asked.clear()
    account = catalogue_step.describe_folders(db, pages + old, CONFIG, run_id=None)
    assert account["described"] == 2 and account["unchanged"] == 1 and len(asked) == 2
