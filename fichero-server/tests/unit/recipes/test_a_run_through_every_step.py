"""One recipe run through every step (`recipes-run.steps.*`, #6222): Find Lines, Leave Out, Read a line, Translate,
Names, Dates, Find the Documents, Statements, Make a vector and Describe for the catalogue, in one Start over three
pages in three folders, each step's own result asserted from the library's rows. Through the public routes and the real
scheduler; only the models are stubs, each at the function the step really calls (found by running it: Find Lines
calls `kraken_runtime.segment_lines`, Read `read_given_lines` on those lines; Translate `llm.vision`; Names and
Statements `chat_structured_with_fallback` where each module imported it, Statements' grammar check spaCy's
`predicate_problem`; the catalogue `llm.chat_with_fallback`;
the vectors the library's `embed_many_unless_current`). A stub patched at a function the step no longer calls lets
the real model run (2026-10-27: the old `segment_to_geometry` stub let real Kraken segment every page, 14 s and 6 GB)."""
# ruff: noqa: F811 -- pytest fixtures imported from the sibling tests are named as test arguments
from __future__ import annotations

import json

import fichero_server.llm as llm
from fichero_server.execution import jobs
from fichero_server.llm import kraken_runtime
from tests.unit.recipes.test_every_stage_resumes_after_a_stop_1134 import (  # noqa: F401  (fixture)
    _all_pages,
    _described,
    _done_pages,
    _folders,
    _memory_is_not_the_question,
    _page_names,
)
from tests.unit.recipes.test_every_step_runs_to_spec import _search, embedded  # noqa: F401  (fixture)
from tests.unit.recipes.test_recipe_execution_to_spec import (  # noqa: F401  (fixtures)
    CLOUD,
    _finished,
    _recipe,
    _save,
    _start,
    engine,
    pages,
)
from tests.unit.workflows.test_one_line_pass_read_many import FOUND

ON_CLOUD = {"model": CLOUD, "runs_on": "cloud:openai"}
TRANSLATE_DONE = {"model_override": CLOUD["model"],
                  "tool_config": {"analyze": {"reading_kind": "transcription", "reading_level": "regularised"}}}
STEPS = [
    {"id": "lines", "job": "find-lines", "model": {"kraken": "blla", "kraken_version": "bundled"}},
    {"id": "leave", "job": "leave-out", "model": {"builtin": "leave-out-rules"}},
    {"id": "read", "job": "read-a-line", "model": {"zenodo": "10.5281/zenodo.13788177"}},
    {"id": "translate", "job": "translate-transliterate-normalise", **ON_CLOUD, "settings": {"target": ["regularised"]}},
    {"id": "names", "job": "find-names-tag-words", **ON_CLOUD},
    {"id": "dates", "job": "work-out-dates"},
    {"id": "find", "job": "find-documents-in-a-folder", "model": {"builtin": "document-finder"},
     "settings": {"accept_above": 0.0}},
    {"id": "statements", "job": "find-statements", **ON_CLOUD},
    {"id": "catalogue", "job": "describe-for-the-catalogue", **ON_CLOUD},
]
READ_AS = "Yten dixo Juan el testigo"


def _models(monkeypatch) -> list:
    """Every model the steps ask, stubbed where it is called; the calls, in order. The Kraken functions no step calls any
    more fail the test if one does."""
    from fichero_server.workflows.tools import extract_all, extract_entities_only, extract_svo_only

    calls: list = []
    monkeypatch.setattr(kraken_runtime, "segment_lines", lambda image_path, **kw: calls.append("segment_lines") or FOUND)
    monkeypatch.setattr(kraken_runtime, "read_given_lines",
                        lambda image_path, model_path, lines, **kw: calls.append("read_given_lines") or [READ_AS] * len(lines))
    for name in ("segment_to_geometry", "recognize_to_geometry", "recognize_lines"):
        monkeypatch.setattr(kraken_runtime, name, (lambda n: lambda *a, **k: calls.append(n))(name))

    async def vision(images, prompt, config, **kw):
        calls.append("vision")
        return READ_AS

    async def structured(*a, schema=None, **kw):
        calls.append(schema.__name__)
        if schema.__name__ == "_EntitiesOnly":
            return schema(people=[{"name": "Juan", "entity_type": "person"}])
        if schema.__name__ == "_PageClaims":
            return schema(items=[{"subject": "Juan", "subject_type": "person", "verb": "dixo", "object": "el testigo",
                                  "source_text": READ_AS}])
        return schema()

    async def describe(material, config=None, system=None, permissive_guardrails=False):
        calls.append("describe")
        return "Title: A box.\nScope and content: Letters."

    for module in (llm, extract_all, extract_entities_only, extract_svo_only):
        if hasattr(module, "chat_structured_with_fallback"):
            monkeypatch.setattr(module, "chat_structured_with_fallback", structured)
    monkeypatch.setattr(llm, "vision", vision)
    monkeypatch.setattr(extract_svo_only, "predicate_problem", lambda *a, **k: calls.append("parse") or None)
    monkeypatch.setattr(llm, "chat_with_fallback", describe)
    return calls


def test_one_start_runs_every_step_and_each_leaves_its_own_result(client, db, pages, tmp_path, engine, embedded,
                                                                  monkeypatch, with_material):
    from fichero_server.finddocs import store as finddocs_store
    from fichero_server.models import Segment
    from fichero_server.models.knowledge import KnowledgeClaim, KnowledgeEntity

    calls = _models(monkeypatch)
    _folders(db, pages)
    _save(client, _recipe(tmp_path, *STEPS, _search()))
    job_id = _start(client)
    run = _finished(client, job_id)

    assert run["state"] == "done", run
    assert run["skipped"] == [] and run["refusals"] == []
    assert {sid: s["state"] for s in run["steps"] for sid in s["steps"]} == {
        s["id"]: "done" for s in [*STEPS, _search()]}
    assert not {"segment_to_geometry", "recognize_to_geometry", "recognize_lines"} & set(calls), calls

    every = _page_names(db, _all_pages(db))
    assert len(every) == 3
    # Find Lines: FOUND's three lines on each page.
    for page in _all_pages(db):
        assert len([s for s in db.query(Segment, document_id=page) if s.kind == "line" and s.deleted_at is None]) >= 3
    for job, card in (("find-lines", None), ("leave-out", None), ("read-a-line", None),
                      ("translate-transliterate-normalise", TRANSLATE_DONE), ("find-names-tag-words", None)):
        assert _done_pages(db, job, card) == every, job
    assert calls.count("read_given_lines") == 3 and calls.count("vision") == 3
    # Names: the person the model named; Statements: its claim (beside the fixture's one).
    assert [e.canonical_name for e in db.query(KnowledgeEntity)] == ["Juan"]
    assert [c.text for c in db.query(KnowledgeClaim) if c.svo_verb == "dixo"] == ["Juan dixo el testigo."] * 3
    assert calls.count("_PageClaims") == 3
    # Find the Documents proposed at least one; every folder described.
    assert sum(len(p.documents) for p in finddocs_store.proposals(db)) >= 1
    # Make a vector: the run's own batches embed every page once (an action's per-page re-embed may follow; it is
    # `embed_unless_current`, a no-op on a page whose vectors are current).
    batches = [json.loads(jobs.read_job(db, c["id"])["detail"])["documents"]
               for c in client.get(f"/api/activity/jobs/{job_id}").json()["children"] if c["kind"] == "make-a-vector"]
    assert sorted(d for b in batches for d in b) == sorted(_all_pages(db))
    assert set(embedded) == set(_all_pages(db))
    assert _described(db) == {"Top", "Box 0", "Box 1"}

    lines = client.get(f"/api/recipes/project/runs/{job_id}/summary").json()["lines"]
    assert "Read 3 of 3 pages" in lines, lines
    assert any(line.startswith("0 pages dated") for line in lines), lines  # Dates ran and found none in the reading
    assert any("Names: 1 People" in line for line in lines), lines
