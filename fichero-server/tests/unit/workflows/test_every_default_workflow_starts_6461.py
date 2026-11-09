"""#6461 workflows are not working: every shipped workflow, started on one page, is accepted or refused in a plain sentence --
never a server error, never dropped without a word."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.unit.recipes.test_recipe_execution_to_spec import pages  # noqa: F401  (fixture)

PRESETS = sorted((Path(__file__).resolve().parents[3] / "src" / "fichero_server" / "resources" / "default_workflows").glob("*.json"))


def _name(path: Path) -> str:
    return json.loads(path.read_text(encoding="utf-8"))["name"]


@pytest.mark.parametrize("path", PRESETS, ids=lambda p: p.stem)
def test_each_default_workflow_starts_or_says_why(client, db, pages, path):  # noqa: F811
    from fichero_server.workflows.workflow_store import WorkflowStore

    workflow = next((w for w in WorkflowStore(db).list_all() if w.name == _name(path)), None)
    assert workflow is not None, f"{_name(path)} is not installed with the shipped workflows"
    answer = client.post("/api/workflow-execution/execute",
                         json={"workflow_id": workflow.id, "inputs": {"selected_doc_ids": [pages[0].id]}})
    assert answer.status_code < 500, f"{_name(path)}: {answer.status_code} {answer.text[:300]}"
    if answer.status_code >= 400:
        detail = answer.json().get("detail")
        sentence = detail.get("message") if isinstance(detail, dict) else detail
        assert isinstance(sentence, str) and sentence.strip(), f"{_name(path)} refused with no sentence: {answer.text[:300]}"


def test_translate_from_a_workflow_translates_a_page_that_has_text_and_says_plainly_when_it_has_none(client, db, pages, monkeypatch):  # noqa: F811
    import time

    from fichero_server.workflows.workflow_store import WorkflowStore

    async def chat(*args, **kwargs):
        return "Hello world"

    monkeypatch.setattr("fichero_server.llm.chat", chat)
    workflow = next(w for w in WorkflowStore(db).list_all() if w.name == "Translate")

    def run(page):
        started = client.post("/api/workflow-execution/execute", json={"workflow_id": workflow.id, "inputs": {"selected_doc_ids": [page.id]}})
        assert started.status_code == 202, started.text
        for _ in range(240):  # 2 minutes: the machine may be loaded (a 30 s wait failed at load 34)
            status = client.get(f"/api/workflow-execution/threads/{started.json()['thread_id']}/status")
            if status.status_code == 200 and status.json()["status"] in ("completed", "failed", "error"):
                return status.json()
            time.sleep(0.5)
        raise AssertionError("the run never ended")

    pages[0].page_content = "Hola mundo"
    db.save(pages[0])
    done = run(pages[0])
    assert done["status"] == "completed" and done["current_state"]["outputs"]["text_translate"]["text"] == "Hello world"
    failed = run(pages[1])  # no text, and no model to read one
    assert failed["status"] == "failed" and "has not been read yet" in failed["error"], failed["error"]
