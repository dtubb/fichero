"""Every recipe step that does not run says why (#6212 item 4), tested to the spec:
`recipes-run.steps.find-lines`, `.leave-out`, `.read-a-line`, `.translate-transliterate-normalise`,
`.find-names-tag-words`, `.work-out-dates`, `.find-documents-in-a-folder`, `.find-statements`, `.make-a-vector`,
`.describe-for-the-catalogue` (docs/contributor_manual/specs/source/recipes-run.md, "Each step: ran, or why not").

WHY: a step with no model says "<step> has no model" with Choose a model, and a step that takes what a model-less
step would have made says it waits for it (`source.onboard.no-model-step-kept`, #5668). Leave Out (lines in, lines
out) and Translate (readings in, readings out) gave what they took, so each met its own take: with Find Lines
model-less, Leave Out was planned to run on no lines and said nothing, and Read each line met "lines" off it.
"""

from __future__ import annotations

import pytest

from fichero_server.db.embeddings import search_embedder
from fichero_server.recipes.start import plan_start, step_names

KRAKEN = {"kraken": "blla", "kraken_version": "bundled"}
READER = {"zenodo": "10.5281/zenodo.13788177"}
SPACY = {"spacy": "es_core_news_sm", "version": "bundled"}


def _base() -> list[dict]:
    return [{"id": "lines", "job": "find-lines", "model": dict(KRAKEN)},
            {"id": "read", "job": "read-a-line", "model": dict(READER)},
            {"id": "names", "job": "find-names-tag-words", "model": dict(SPACY)}]


def _plan(steps: list[dict]) -> dict:
    return plan_start({"fichero_recipe": 1, "id": "t/r", "version": "0.1.0", "title": "t", "steps": steps},
                      stays_local=True)


def _ran(plan: dict) -> set[str]:
    return {sid for run in plan["runs"] for sid in run["steps"]}


@pytest.mark.parametrize("job, title", [
    ("find-lines", "Find lines"), ("read-a-line", "Read each line"),
    ("translate-transliterate-normalise", "Translate, transliterate or normalise"),
    ("find-names-tag-words", "Find names"), ("find-statements", "Find statements"),
    ("make-a-vector", "Make vectors for search"), ("describe-for-the-catalogue", "Describe for the catalogue")])
def test_a_step_with_no_model_is_skipped_saying_so_with_choose_a_model(job, title):
    steps = [s for s in _base() if s["job"] != job] + [{"id": "x", "job": job, "model": None}]
    plan = _plan(steps)
    (said,) = [s for s in plan["skipped"] if s["step"] == "x"]
    assert said["why"].startswith(f"{title} has no model") and said["fix"] == "choose-model"
    assert "x" not in _ran(plan)


@pytest.mark.parametrize("job, model, waited_job, waited_title", [
    ("leave-out", None, "find-lines", "Find lines"),
    ("translate-transliterate-normalise", SPACY, "read-a-line", "Read each line"),
    ("work-out-dates", None, "find-names-tag-words", "Find names"),
    ("find-documents-in-a-folder", None, "read-a-line", "Read each line"),
    ("find-statements", SPACY, "read-a-line", "Read each line"),
    ("make-a-vector", "embedder", "read-a-line", "Read each line"),
    ("describe-for-the-catalogue", SPACY, "read-a-line", "Read each line")])
def test_a_step_whose_input_has_no_model_waits_for_it_and_does_not_run(job, model, waited_job, waited_title):
    steps = _base()
    for s in steps:
        if s["job"] == waited_job:
            s["model"] = None
    step = {"id": "x", "job": job}
    if model is not None:
        step["model"] = {"hf": search_embedder(), "revision": "main"} if model == "embedder" else dict(model)
    plan = _plan([*steps, step])
    why = {s["step"]: s["why"] for s in plan["skipped"]}
    assert why.get("x", "").startswith(f"{step_names({'steps': [step]})['x']} waits for {waited_title}, which has no model yet"), why
    assert "x" not in _ran(plan), plan["runs"]


def test_read_does_not_meet_its_lines_off_leave_out_when_find_lines_has_no_model():
    steps = [{"id": "lines", "job": "find-lines", "model": None}, {"id": "leave", "job": "leave-out"},
             {"id": "read", "job": "read-a-line", "model": dict(READER)}]
    plan = _plan(steps)
    assert _ran(plan) == set(), plan["runs"]
    assert {s["step"] for s in plan["skipped"]} == {"lines", "leave", "read"}



def _summary(**figures):
    from fichero_server.recipes.run_view import RecipeRunSummary

    return RecipeRunSummary(**{"job_id": "j", "state": "done", "finished": True, "pages": 5, "pages_read": 5,
                               "names": [], "dates": 0, "statements": 0, "failed": [], "pages_failed": 0,
                               "skipped": [], "not_run": [], **figures})


def test_dates_that_ran_and_dated_nothing_say_0_pages_dated_and_a_run_without_it_says_nothing():
    """`recipes-run.steps.work-out-dates`: the stage ran, so its figure is said even at 0; without the stage no line."""
    from fichero_server.recipes.run_view import _lines

    assert "0 pages dated" in _lines(_summary(), 0, ran={"read-a-line", "work-out-dates"})
    assert not any("dated" in w for w in _lines(_summary(), 0, ran={"read-a-line"}))
    assert "1 page dated" in _lines(_summary(pages_dated=1), 0, ran={"read-a-line", "work-out-dates"})
