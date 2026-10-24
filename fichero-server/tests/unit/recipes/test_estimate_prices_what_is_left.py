"""The plan prices a run on the pages it has still to do, not on pages already done: the price, the cap check and the
run agree (a finished project is not asked for spend it will not make)."""
from __future__ import annotations

import pytest

from fichero_server.models import Artifact, DocType, Document
from fichero_server.recipes.done import todo_counts
from fichero_server.recipes.start import estimate
from fichero_server.workflows.tools.analyze import tool_config_for

MODEL = "claude-haiku-4-5"


def _cards():
    base = {"card": "workflow", "runs_on": "cloud:anthropic", "model_override": MODEL, "provider_override": "anthropic",
            "workflow_id": None}
    return [{**base, "job": "read-a-page", "steps": ["read-a-page"], "workflow": "Read"},
            {**base, "job": "translate-transliterate-normalise", "steps": ["translate-transliterate-normalise"],
             "workflow": "Translate", "tool_config": {}}]


def _pages(db, n, done):
    kind = tool_config_for(None, None).artifact_type
    ids = []
    for i in range(n):
        doc = Document(name=f"p{i}", doc_type=DocType.page, page_content="")
        db.save(doc)
        ids.append(doc.id)
        if i < done:
            for t in ("transcription", kind):
                db.save(Artifact(document_id=doc.id, artifact_type=t, content="x", model=MODEL))
    return ids


def _price(db):
    plan = {"runs": _cards()}
    todo = todo_counts(db, plan)
    return todo, estimate(plan["runs"], len(db.unit_of_work_ids()), todo=todo)


def test_five_done_and_one_new_prices_one_page(db):
    _pages(db, 6, 5)
    todo, est = _price(db)
    assert todo == {"read-a-page": 1, "translate-transliterate-normalise": 1}
    assert [r["pages"] for r in est["runs"]] == [1, 1]
    full = estimate(_cards(), 6)
    assert est["total_cost_usd"] == pytest.approx(full["total_cost_usd"] / 6)


def test_a_finished_project_prices_nothing(db):
    _pages(db, 6, 6)
    todo, est = _price(db)
    assert todo == {"read-a-page": 0, "translate-transliterate-normalise": 0}
    assert est["total_cost_usd"] == 0.0
