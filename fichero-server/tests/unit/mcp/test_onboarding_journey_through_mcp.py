"""The onboarding journey an agent makes, driven through the generated MCP tools end to end (the week plan's "MCP end
to end"), tested to the spec: `openapi.mcp.onboarding-journey` (docs/contributor_manual/specs/harness/
surfaces-from-openapi.md).

WHY: the overnight walks drove onboarding through MCP and kept finding the same kinds of fault one at a time: a tool
the journey needs not on the default surface, an answer too fat for an agent, a refusal that reads as a traceback.
One walk, every step, in-process: open the project, save Set Up, the start plan, Start, the run's status and summary,
Find the Documents' proposals, accept one, undo it, the training preview. No model is loaded: the journey's recipe is
the step that needs none (Find the Documents), on pages whose text is already read.
"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from mcp import types

from fichero_cli import FicheroClient
from fichero_mcp import server as mcp_server
from fichero_server.execution import jobs
from fichero_server.finddocs import job as finddocs_job
from fichero_server.recipes import runner
from tests.unit.finddocs.boxes import correspondence_box
from tests.unit.finddocs.test_find_documents_to_spec import _project

#: What each step's answer may weigh, from what the step needs (`openapi.mcp.answers-fit-an-agent`'s 64 KB is the
#: outer bound; these are the journey's own).
CEILING = {
    "fichero_use_library": 4_000,
    "fichero_recipes_save_project_setup": 16_000,
    "fichero_recipes_get_start_plan": 32_000,
    "fichero_recipes_start_project": 32_000,
    "fichero_recipes_run_status": 16_000,
    "fichero_recipes_run_summary": 8_000,
    "fichero_find_documents_list_proposals": 32_000,
    "fichero_find_documents_accept_proposal": 8_000,
    "fichero_actions_undo": 8_000,
    "fichero_training_preview_set": 16_000,
    "fichero_documents_get_children": 16_000,
}
RECIPE = {"fichero_recipe": 1, "id": "t/journey", "version": "0.1.0", "title": "Journey", "suits": {"material": "text"},
          "steps": [{"id": "organise", "job": "find-documents-in-a-folder"}]}


@pytest.fixture
def agent(client, test_package, monkeypatch):
    def forward(request: httpx.Request) -> httpx.Response:
        answered = client.request(request.method, request.url.path, params=list(request.url.params.multi_items()),
                                  content=request.content or None,
                                  headers={"content-type": request.headers.get("content-type", "application/json")})
        return httpx.Response(answered.status_code, content=answered.content,
                              headers={"content-type": answered.headers.get("content-type", "application/json")})

    def build() -> FicheroClient:
        return FicheroClient(base_url="http://test", library_path=str(test_package), token="t",
                             transport=httpx.MockTransport(forward))

    monkeypatch.setattr(mcp_server, "_client", build)
    monkeypatch.setattr(mcp_server, "_mutating_client", build)
    return mcp_server.mcp


def _call(server, name: str, arguments: dict, *, refused: bool = False):
    """One tool call as an agent makes it: the tool is listed, its answer parses and is lean, and a refusal is
    words, never a traceback."""
    listed = {tool.name for tool in asyncio.run(server.list_tools())}
    assert name in listed, f"{name} is not on the MCP surface the journey uses"
    handler = server._mcp_server.request_handlers[types.CallToolRequest]
    result = asyncio.run(handler(types.CallToolRequest(
        method="tools/call", params=types.CallToolRequestParams(name=name, arguments=arguments)))).root
    text = "".join(getattr(c, "text", "") for c in result.content)
    assert "Traceback" not in text and 'File "' not in text, (name, text[:500])
    if refused:
        assert result.isError, (name, text[:300])
        assert len(text.split()) >= 4, f"{name} refused without saying why: {text!r}"
        return text
    assert result.isError is False, (name, text[:500])
    assert len(text.encode()) <= CEILING[name], f"{name} answered {len(text.encode()):,} bytes"
    return json.loads(text)


def _run_by_hand(db, job_id):
    kind, subject = db.execute_fetchone("SELECT kind, subject FROM jobs WHERE id = ?", [job_id])
    db.execute("UPDATE jobs SET state = 'running' WHERE id = ? AND state = 'waiting'", [job_id])
    return jobs.KINDS[kind].run(db, subject)


def test_the_onboarding_journey_through_mcp(agent, client, db, tmp_path, test_package, jobs_run_by_the_test,
                                            monkeypatch):
    pages, _truth, _groups = correspondence_box()
    folder, ids = _project(db, tmp_path, pages)
    started = finddocs_job.start

    def start_and_run(db_, request, **kw):  # the scheduler, by hand, as the recipe tests run it
        job_id = started(db_, request, **kw)
        _run_by_hand(db_, job_id)
        db_.execute("UPDATE jobs SET state = 'done' WHERE id = ?", [job_id])
        return job_id

    monkeypatch.setattr(finddocs_job, "start", start_and_run)

    # 1. Open the project.
    _call(agent, "fichero_use_library", {"path": str(test_package)})
    # 2. Save Set Up's answers and recipe.
    saved = _call(agent, "fichero_recipes_save_project_setup",
                  {"answers": {"purposes": ["transcribe"], "languages": ["es"], "scripts": ["Latn"], "loose_pages": True,
                               "materials": ["text"]},
                   "recipe": RECIPE})
    assert saved["recipe"]["steps"][0]["id"] == "organise"
    # 3. The start plan, before anything runs.
    plan = _call(agent, "fichero_recipes_get_start_plan", {})
    assert not plan["refusals"], plan["refusals"]
    assert [r["job"] for r in plan["runs"]] == ["find-documents-in-a-folder"]
    # 4. Start.
    start = _call(agent, "fichero_recipes_start_project", {})
    run_id = start["started"]["job_id"]
    _run_by_hand(db, run_id)
    # 5. The run's status and summary.
    status = _call(agent, "fichero_recipes_run_status", {"job_id": run_id})
    assert status["steps"][0]["state"] == "done", status["steps"]
    summary = _call(agent, "fichero_recipes_run_summary", {"job_id": run_id})
    assert summary["lines"]
    # 6. Find the Documents' proposals.
    proposals = _call(agent, "fichero_find_documents_list_proposals", {"folder_id": folder.id})
    (proposal,) = proposals["items"]
    assert len(proposal["documents"]) >= 2
    # 7. Accept one, then 8. undo it.
    accepted = _call(agent, "fichero_find_documents_accept_proposal",
                      {"proposal_id": proposal["id"], "document_indexes": [0]})
    assert accepted.get("audit_id"), accepted
    _call(agent, "fichero_actions_undo", {"audit_id": accepted["audit_id"]})
    again = _call(agent, "fichero_find_documents_list_proposals", {"folder_id": folder.id})["items"][0]
    assert again["documents"][0]["state"] == "proposed"
    # The folder's pages, as an agent lists them: lean.
    _call(agent, "fichero_documents_get_children", {"doc_id": folder.id})
    # 9. The training preview: nothing read by Kraken here, said in numbers.
    preview = _call(agent, "fichero_training_preview_set",
                    {"teacher": "kraken-mccatmus", "scope_ids": [folder.id]})
    assert preview["pages"] == 0 and preview["missing"]

    # Refusals, in words: a proposal that is not there, and a training start with nothing to train on (#5699).
    _call(agent, "fichero_find_documents_accept_proposal", {"proposal_id": "nope", "document_indexes": [0]}, refused=True)
    said = _call(agent, "fichero_training_start_kraken_here",
                 {"scope_ids": [folder.id], "teacher": "kraken-mccatmus", "epochs": 1}, refused=True)
    assert "nothing to train on" in said
