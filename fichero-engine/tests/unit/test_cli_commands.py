"""Unit tests for the fichero CLI command tree and output formatters.

The FicheroClient is replaced with an in-memory fake so the CLI is exercised
without a live backend.
"""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from fichero import __main__ as cli
from fichero.cli import FicheroError
from fichero.cli.formatters import render

runner = CliRunner()


class FakeClient:
    """Records construction kwargs and call args; returns canned responses."""

    instances: list["FakeClient"] = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.calls: list[tuple] = []
        FakeClient.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def close(self):
        pass

    # -- recorded operations --------------------------------------------
    def health(self):
        self.calls.append(("health",))
        return {"status": "ok"}

    def list_documents(self, **kw):
        self.calls.append(("list_documents", kw))
        return [{"id": "d1", "title": "Doc One", "doc_type": "file"}]

    def get_document(self, doc_id):
        self.calls.append(("get_document", doc_id))
        return {"id": doc_id, "title": "Doc One"}

    def import_file(self, path, parent_id=None):
        self.calls.append(("import_file", path, parent_id))
        return {"id": "d99", "filename": str(path)}

    def list_workflows(self):
        self.calls.append(("list_workflows",))
        return [
            {"id": "wf-1", "name": "Catalogue"},
            {"id": "wf-2", "name": "Transcribe"},
        ]

    def run_workflow(self, workflow_id, inputs=None, **kw):
        self.calls.append(("run_workflow", workflow_id, inputs, kw))
        return {"thread_id": "t-1", "workflow_id": workflow_id, "status": "accepted"}

    def execution_status(self, thread_id):
        self.calls.append(("execution_status", thread_id))
        # First poll: running. Second: completed.
        polls = [c for c in self.calls if c[0] == "execution_status"]
        status = "running" if len(polls) < 2 else "completed"
        return {"thread_id": thread_id, "status": status}

    def list_artifacts(self, doc_id, **kw):
        self.calls.append(("list_artifacts", doc_id, kw))
        return {"artifacts": [{"id": "a1", "artifact_type": "transcription"}]}

    def list_entities(self, **kw):
        self.calls.append(("list_entities", kw))
        return [{"id": "e1", "name": "Bogotá", "entity_type": "place"}]

    def list_claims(self, **kw):
        self.calls.append(("list_claims", kw))
        return [{"id": "c1", "subject": "X", "claim_type": "fact"}]

    def document_inspector(self, doc_id):
        self.calls.append(("document_inspector", doc_id))
        return {
            "entities": [{"id": "e1", "name": "Bogotá"}],
            "claims": [{"id": "c-other", "subject": "should not appear"}],
            "artifacts": [{"id": "a-other"}],
        }

    def kg_search(self, query, **kw):
        self.calls.append(("kg_search", query, kw))
        return {"results": [{"id": "r1", "title": "hit"}]}

    def search(self, query, **kw):
        self.calls.append(("search", query, kw))
        return {"results": [{"id": "d1", "title": "Doc One"}]}

    def recent_activity(self, **kw):
        self.calls.append(("recent_activity", kw))
        return [{"id": "act1", "status": "completed"}]


@pytest.fixture(autouse=True)
def _patch_client(monkeypatch):
    FakeClient.instances = []
    monkeypatch.setattr(cli, "FicheroClient", FakeClient)
    # Make `workflow run --wait` polling instant.
    monkeypatch.setattr(cli.time, "sleep", lambda _seconds: None)
    yield


def _last_client() -> FakeClient:
    return FakeClient.instances[-1]


# -- basic commands --------------------------------------------------------
def test_health_human_output():
    result = runner.invoke(cli.app, ["health"])
    assert result.exit_code == 0
    assert "status: ok" in result.output
    assert _last_client().calls == [("health",)]


def test_health_json_output():
    result = runner.invoke(cli.app, ["--json", "health"])
    assert result.exit_code == 0
    assert json.loads(result.output) == {"status": "ok"}


def test_global_options_passed_to_client():
    result = runner.invoke(
        cli.app,
        ["--library", "/tmp/L.fichero", "--base-url", "http://x", "--token", "tk", "health"],
    )
    assert result.exit_code == 0
    assert _last_client().kwargs == {
        "base_url": "http://x",
        "library_path": "/tmp/L.fichero",
        "token": "tk",
    }


def test_docs_list_forwards_filters():
    result = runner.invoke(cli.app, ["docs", "list", "--parent", "p1", "--limit", "3"])
    assert result.exit_code == 0
    _, kw = _last_client().calls[0]
    assert kw["parent_id"] == "p1"
    assert kw["limit"] == 3
    assert "Doc One" in result.output


def test_docs_get_passes_id():
    result = runner.invoke(cli.app, ["docs", "get", "abc"])
    assert result.exit_code == 0
    assert ("get_document", "abc") in _last_client().calls


def test_import_passes_path_and_parent():
    result = runner.invoke(cli.app, ["import", "/tmp/file.pdf", "--parent", "f1"])
    assert result.exit_code == 0
    assert ("import_file", "/tmp/file.pdf", "f1") in _last_client().calls


# -- workflow run ----------------------------------------------------------
def test_workflow_run_resolves_name_to_id():
    result = runner.invoke(cli.app, ["workflow", "run", "Catalogue", "doc-7"])
    assert result.exit_code == 0
    run_call = next(c for c in _last_client().calls if c[0] == "run_workflow")
    assert run_call[1] == "wf-1"
    assert run_call[2] == {"files": ["doc-7"]}


def test_workflow_run_unknown_name_errors():
    result = runner.invoke(cli.app, ["workflow", "run", "Nope", "doc-7"])
    assert result.exit_code == 1
    assert "No workflow named 'Nope'" in result.output


def test_workflow_run_wait_polls_until_terminal():
    result = runner.invoke(cli.app, ["workflow", "run", "Catalogue", "doc-7", "--wait"])
    assert result.exit_code == 0
    polls = [c for c in _last_client().calls if c[0] == "execution_status"]
    assert len(polls) >= 2
    assert "status: completed" in result.output


def test_workflow_run_accepts_id_directly():
    result = runner.invoke(cli.app, ["workflow", "run", "wf-2", "doc-7"])
    assert result.exit_code == 0
    run_call = next(c for c in _last_client().calls if c[0] == "run_workflow")
    assert run_call[1] == "wf-2"


def test_workflow_run_wait_tolerates_404_then_completes(monkeypatch):
    """The backend may 404 the status endpoint before its checkpoint exists.

    Treat 404 as "not yet" — keep polling until a real status appears or a
    non-404 error is raised. Without this, fast-completing runs blow up.
    """
    calls = {"count": 0}

    def flaky_status(self, thread_id):
        self.calls.append(("execution_status", thread_id))
        calls["count"] += 1
        if calls["count"] == 1:
            raise FicheroError("not ready", status_code=404)
        return {"thread_id": thread_id, "status": "completed"}

    monkeypatch.setattr(FakeClient, "execution_status", flaky_status)
    result = runner.invoke(cli.app, ["workflow", "run", "Catalogue", "doc-7", "--wait"])
    assert result.exit_code == 0
    # Both polls must have happened — proves the 404 didn't bail us out and the
    # subsequent success was observed.
    assert calls["count"] >= 2
    polls = [c for c in _last_client().calls if c[0] == "execution_status"]
    assert len(polls) >= 2
    assert "status: completed" in result.output


def test_workflow_run_wait_propagates_non_404_errors(monkeypatch):
    """A 500 (or any non-404) during polling should bail out, not loop."""

    def boom(self, thread_id):
        self.calls.append(("execution_status", thread_id))
        raise FicheroError("kaboom", status_code=500)

    monkeypatch.setattr(FakeClient, "execution_status", boom)
    result = runner.invoke(cli.app, ["workflow", "run", "Catalogue", "doc-7", "--wait"])
    assert result.exit_code == 1
    assert "kaboom" in result.output


def test_workflow_run_wait_raises_on_all_404_exhaustion(monkeypatch):
    """If the poll budget is exhausted on nothing but 404s, surface a timeout —
    do NOT return silently with empty output, which would mask the failure."""

    def perma_404(self, thread_id):
        self.calls.append(("execution_status", thread_id))
        raise FicheroError("not ready", status_code=404)

    monkeypatch.setattr(FakeClient, "execution_status", perma_404)
    # Shrink the poll budget so the test is fast.
    monkeypatch.setattr(cli, "_POLL_MAX_ATTEMPTS", 3)
    result = runner.invoke(cli.app, ["workflow", "run", "Catalogue", "doc-7", "--wait"])
    assert result.exit_code == 1
    assert "Timed out" in result.output
    assert "fichero activity" in result.output


# -- kg / search / activity ------------------------------------------------
def test_kg_entities_uses_inspector():
    """`kg entities <doc-id>` hits the doc-scoped inspector endpoint."""
    result = runner.invoke(cli.app, ["kg", "entities", "d5"])
    assert result.exit_code == 0
    assert ("document_inspector", "d5") in _last_client().calls


def test_kg_entities_filters_to_entities_only():
    """Output must show entities only, not the full inspector blob."""
    result = runner.invoke(cli.app, ["--json", "kg", "entities", "d5"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert isinstance(payload, list)
    assert payload == [{"id": "e1", "name": "Bogotá"}]
    # Sibling fields from the inspector must not leak through.
    assert "should not appear" not in result.output
    assert "a-other" not in result.output


def test_kg_claims_positional_doc_id():
    """`kg claims <doc-id>` passes doc-id as source_document_id."""
    result = runner.invoke(cli.app, ["kg", "claims", "d5"])
    assert result.exit_code == 0
    call = next(c for c in _last_client().calls if c[0] == "list_claims")
    assert call[1]["source_document_id"] == "d5"


def test_kg_entities_requires_doc_id():
    """The doc-id is required — bare `kg entities` should exit non-zero."""
    result = runner.invoke(cli.app, ["kg", "entities"])
    assert result.exit_code != 0


def test_kg_search_passes_query():
    result = runner.invoke(cli.app, ["kg", "search", "land reform"])
    assert result.exit_code == 0
    call = _last_client().calls[0]
    assert call[0] == "kg_search" and call[1] == "land reform"


def test_search_command():
    result = runner.invoke(cli.app, ["search", "archive", "--limit", "5"])
    assert result.exit_code == 0
    call = _last_client().calls[0]
    assert call[1] == "archive" and call[2]["limit"] == 5


def test_activity_command():
    result = runner.invoke(cli.app, ["activity"])
    assert result.exit_code == 0
    assert "completed" in result.output


# -- error handling --------------------------------------------------------
def test_client_error_exits_nonzero(monkeypatch):
    def boom(self):
        raise FicheroError("Cannot connect to the Fichero backend")

    monkeypatch.setattr(FakeClient, "health", boom)
    result = runner.invoke(cli.app, ["health"])
    assert result.exit_code == 1


# -- formatters ------------------------------------------------------------
def test_render_json_is_valid():
    out = render({"b": 2, "a": 1}, as_json=True)
    assert json.loads(out) == {"a": 1, "b": 2}


def test_render_list_one_line_per_item():
    out = render([{"id": "d1", "title": "One"}, {"id": "d2", "title": "Two"}])
    assert out.splitlines() == ["- d1  One", "- d2  Two"]


def test_render_unwraps_envelope():
    out = render({"documents": [{"id": "d1", "name": "N"}]})
    assert out.startswith("documents (1):")
    assert "- d1  N" in out


def test_render_empty_list():
    assert render([]) == "(empty)"


def test_render_none():
    assert render(None) == "(no data)"


def test_render_nested_dict():
    out = render({"id": "d1", "meta": {"pages": 3}})
    assert "id: d1" in out
    assert "meta:" in out
    assert "pages: 3" in out
