"""`designer.budget.estimate-from-booked-usage` (#6294): once the project has booked calls of the same model and job, the per-page figure is the
median booked cost a page, labelled measured with the page count; until then the token assumption, labelled assumed. No margin on top."""
from __future__ import annotations

import json

import pytest

from fichero_server.execution import jobs
from fichero_server.recipes import booked_cost
from fichero_server.recipes.start import estimate

MODEL, PROVIDER = "claude-haiku-4-5", "anthropic"


def _run():
    return {"card": "workflow", "runs_on": "cloud:anthropic", "model_override": MODEL, "provider_override": PROVIDER, "workflow_id": None,
            "job": "read-a-page", "steps": ["read-a-page"], "workflow": "Read"}


def _book(db, page, tokens_in, tokens_out, n=1, model=MODEL):
    jobs._ensure(db)
    for i in range(n):
        usage = [{"provider": PROVIDER, "model": model, "kind": "chat", "input_tokens": tokens_in, "output_tokens": tokens_out,
                  "total_tokens": tokens_in + tokens_out, "cache_read_tokens": 0, "estimated": False, "place": None}]
        db.execute("INSERT INTO jobs (id, kind, subject, state, created_at, finished_at, detail) VALUES (?, 'read-a-page', ?, 'done', "
                   "now(), now(), ?)", [f"{page}-{i}", page, json.dumps({"usage": usage})])


def test_with_nothing_booked_the_figure_is_assumed(db):
    assert booked_cost.for_workflows(db, [_run()]) == {}
    (row,) = estimate([_run()], 10)["runs"]
    assert row["basis_kind"] == "assumed" and row["measured_pages"] is None and "assumed" in row["basis_words"]


def test_booked_pages_replace_the_assumption_with_their_median_and_say_how_many(db):
    for page in ("a", "b", "c"):
        _book(db, page, 100_000, 10_000)  # dear pages: well above the token assumption
    found = booked_cost.for_workflows(db, [_run()])
    per, pages = found[("read-a-page", PROVIDER, MODEL)]
    assert pages == 3 and per > 0
    assumed = estimate([_run()], 10)["runs"][0]
    (row,) = estimate([_run()], 10, booked=found)["runs"]
    assert row["basis_kind"] == "measured" and row["measured_pages"] == 3 and row["cost_usd"] == pytest.approx(per * 10)
    assert row["cost_usd"] > assumed["cost_usd"], "the booked figure is higher than the assumption here, and no margin is added"
    assert "measured on 3 pages of this project" in row["basis_words"]


def test_a_page_with_several_rows_counts_once_and_another_model_is_not_mixed_in(db):
    _book(db, "a", 1000, 100, n=3)
    _book(db, "b", 5_000_000, 100, model="other-model")
    per, pages = booked_cost.per_page(db, "read-a-page", PROVIDER, MODEL)
    assert pages == 1 and per < 1, "the other model's five million tokens are not in this model's median"
