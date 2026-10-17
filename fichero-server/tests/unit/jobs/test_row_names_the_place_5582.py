"""A call row and every row above it name the place its calls ran, with how many calls went to each
(#5582, `ai.where.row-names-the-place`)."""
from __future__ import annotations

import json

from fichero_server.execution import jobs


def _call(db, parent, place):
    job_id = jobs._insert(db, "ask-a-model", "page", "openai:gpt-5", "workflow")
    db.execute("UPDATE jobs SET parent_id = ?, state = 'done', detail = ? WHERE id = ?", [
        parent, json.dumps({"usage": [{"provider": "openai", "model": "gpt-5", "kind": "chat", "input_tokens": 10,
                                       "output_tokens": 5, "total_tokens": 15, "place": place}]}), job_id])
    return job_id


def test_a_row_names_the_places_of_the_calls_under_it_and_counts_them(db):
    jobs._ensure(db)
    step = jobs._insert(db, "workflow-step", "run:step", None, "workflow")
    _call(db, step, "provider")
    _call(db, step, "provider")
    _call(db, step, "own_machine")

    root = jobs.tree(db, step)

    assert root["places"] == {"provider": 2, "own_machine": 1}
    leaf = root["children"][0]
    assert leaf["places"] == {"provider": 1}
