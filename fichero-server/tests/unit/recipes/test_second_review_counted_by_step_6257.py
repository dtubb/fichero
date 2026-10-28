"""A second Review the reading step (`correct-2`, #6257) is counted and priced by its own step, never by the first's."""
from __future__ import annotations

from fichero_server.models import Artifact, DocType, Document
from fichero_server.recipes import done
from fichero_server.recipes.start import estimate


def _card(step, model):
    return {"card": "workflow", "job": "correct", "steps": [step], "runs_on": "cloud:anthropic", "model_override": model,
            "provider_override": "anthropic", "workflow_id": None, "workflow": "Review"}


def _pages(db, n, reviewed_by_first):
    ids = []
    for i in range(n):
        doc = Document(name=f"p{i}", doc_type=DocType.page, page_content="")
        db.save(doc)
        ids.append(doc.id)
        if i < reviewed_by_first:
            db.save(Artifact(document_id=doc.id, artifact_type=done.REVIEWED, content="x", model="claude-haiku-4-5"))
    return ids


def test_each_review_step_has_its_own_pages_left(db):
    _pages(db, 4, 3)
    plan = {"runs": [_card("correct", "claude-haiku-4-5"), _card("correct-2", "claude-sonnet-4-5")]}
    todo = done.todo_counts(db, plan)
    assert todo == {"correct": 1, "correct-2": 4}
    rows = estimate(plan["runs"], 4, todo=todo)["runs"]
    assert [r["pages"] for r in rows] == [1, 4]


def test_a_review_by_an_unknown_model_is_not_this_steps(db):
    (page,) = _pages(db, 1, 1)
    assert done._has_review(db, page, None, None) is False


def test_a_first_review_step_with_no_model_still_takes_a_pages_review_as_done(db):
    (page,) = _pages(db, 1, 1)
    assert done._has_review(db, page, None, None, "correct") is True
    assert done._has_review(db, page, None, None, "correct-2") is False
