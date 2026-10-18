"""`source.recipe.start-runs-the-steps` (#5684): a step that cannot start fails alone, in one plain line; and Kraken
that cannot load its libraries is not available.

Spec: docs/contributor_manual/specs/source/models-chains-and-projects.md. WHY (2026-10-11, the MCP onboarding walk):
Find Regions could not start (scipy's library would not load in that engine's Python) and the whole run ended;
Names, Dates, Organise and Search each said "the run ended before this step: <the raw dlopen text>" (~12 KB over
run_status), the Activity row's reason was the dyld text, and kraken_status said available. Through the Start route
and the real runner; the steps' workflows are stubbed, one of them raising as the dlopen did.
"""
from __future__ import annotations

import pytest

from tests.unit.recipes.test_recipe_runs_to_spec import (  # noqa: F401  (fixtures)
    RECIPE, _finished, _save, _start, pages, steps,
)

DLOPEN = ("dlopen(/Users/x/.venv/lib/python3.12/site-packages/scipy/linalg/_flapack.cpython-312-darwin.so, 0x0002): "
          "Library not loaded: @rpath/libgfortran.5.dylib\n  Referenced from: <...>\n" + "  Reason: tried: ...\n" * 200)


def test_a_step_that_cannot_start_fails_alone_in_one_plain_line(client, db, pages, steps):
    _save(client, RECIPE)
    plain_run = steps.run

    def run(db_, card, documents, parent):
        if "correct" in card["steps"]:
            steps.ran.append(card["steps"])
            raise ImportError(DLOPEN)
        return plain_run(db_, card, documents, parent)

    steps.run = run
    from fichero_server.recipes import runner

    runner._run_workflow = run  # the fixture's monkeypatch restores the real one after the test
    run_ = _finished(client, _start(client)["started"]["job_id"])

    assert ["names"] in steps.ran, "a step that does not need Correct still runs"
    state = {tuple(s["steps"]): s for s in run_["steps"]}
    failed = state[("correct",)]
    assert failed["state"] == "failed"
    assert "could not start" in failed["why"] and "\n" not in failed["why"] and len(failed["why"]) < 200, failed
    assert "dlopen" not in failed["why"] and "dlopen" not in (run_["reason"] or "")
    assert all("dlopen" not in (s.get("why") or "") for s in run_["steps"])


def test_kraken_that_cannot_load_its_libraries_is_not_available(client, monkeypatch):
    pytest.importorskip("kraken")  # without Kraken at all, the status says it is not bundled, before any library
    from fichero_server.llm import kraken_runtime

    kraken_runtime._libraries_load.cache_clear()
    monkeypatch.setattr(kraken_runtime, "_NATIVE_PROBE", "scipy._a_library_that_will_not_load_5684")
    try:
        body = client.get("/api/local-models/kraken/status").json()
    finally:
        kraken_runtime._libraries_load.cache_clear()
    assert body["available"] is False
    assert "would not load" in body["reason"] and "dlopen" not in body["reason"]
