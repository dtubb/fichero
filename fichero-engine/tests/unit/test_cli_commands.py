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
from fichero.models import LibraryCreateResponse, Workflow

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
        # Real FicheroClient.list_workflows() returns list[Workflow]; the fake
        # must match the typed contract or _resolve_workflow's attribute access
        # fails.
        self.calls.append(("list_workflows",))
        return [
            Workflow.model_validate({"id": "wf-1", "name": "Catalogue"}),
            Workflow.model_validate({"id": "wf-2", "name": "Transcribe"}),
        ]

    def run_workflow(self, workflow_id, inputs=None, **kw):
        self.calls.append(("run_workflow", workflow_id, inputs, kw))
        return {"thread_id": "t-1", "workflow_id": workflow_id, "status": "accepted"}

    def execution_status(self, thread_id):
        self.calls.append(("execution_status", thread_id))
        # The status endpoint is unreliable mid-run (#1088): it reports
        # "completed" whenever a checkpoint has no pending writes. The fake
        # mirrors that flakiness — it always says "completed" so the wait
        # loop is forced to consult the activity log to know the truth.
        return {
            "thread_id": thread_id,
            "workflow_id": "wf-1",
            "workflow_name": "Catalogue",
            "status": "completed",
            "current_state": {"final": True},
        }

    def list_activities(self, *, thread_id=None, types=None, limit=100):
        self.calls.append(("list_activities", thread_id, types, limit))
        # Mimic the executor: emit a workflow_completed event only after
        # the second poll, so the wait loop has to actually wait.
        polls = [c for c in self.calls if c[0] == "list_activities"]
        if len(polls) < 2:
            return []
        return [
            {
                "id": "act-end",
                "type": "workflow_completed",
                "thread_id": thread_id,
                "workflow_id": "wf-1",
            }
        ]

    def get_artifact(self, artifact_id):
        self.calls.append(("get_artifact", artifact_id))
        from fichero.models import Artifact

        return Artifact.model_validate(
            {
                "id": artifact_id,
                "document_id": "doc-7",
                "artifact_type": "transcription",
                "content": "hello world",
                "version": 2,
                "provider": "openai",
                "model": "gpt-4o",
                "reviewed": False,
            }
        )

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

    def create_library(self, path):
        # Real client returns LibraryCreateResponse — keep the typed
        # contract so the CLI's render() goes through the model_dump path.
        self.calls.append(("create_library", path))
        return LibraryCreateResponse(
            path=path, created=True, tables_initialized=True
        )


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
    assert run_call[2] == {"selected_doc_ids": ["doc-7"]}


def test_workflow_run_unknown_name_errors():
    result = runner.invoke(cli.app, ["workflow", "run", "Nope", "doc-7"])
    assert result.exit_code == 1
    assert "No workflow named 'Nope'" in result.output


def test_workflow_run_wait_polls_until_terminal():
    result = runner.invoke(cli.app, ["workflow", "run", "Catalogue", "doc-7", "--wait"])
    assert result.exit_code == 0
    # The wait loop now polls the activity log (#1088). The fake emits
    # workflow_completed on the second call, so we expect at least two polls.
    polls = [c for c in _last_client().calls if c[0] == "list_activities"]
    assert len(polls) >= 2
    assert "status: completed" in result.output


def test_workflow_run_accepts_id_directly():
    result = runner.invoke(cli.app, ["workflow", "run", "wf-2", "doc-7"])
    assert result.exit_code == 0
    run_call = next(c for c in _last_client().calls if c[0] == "run_workflow")
    assert run_call[1] == "wf-2"


def test_workflow_run_wait_tolerates_404_status_endpoint(monkeypatch):
    """A 404 from the status endpoint must NOT abort the wait — fast or
    empty runs may finish before any checkpoint is written, so the activity
    log is the real signal. Status 404 is "not ready yet, keep polling".
    """

    def status_404(self, thread_id):
        self.calls.append(("execution_status", thread_id))
        raise FicheroError("not ready", status_code=404)

    monkeypatch.setattr(FakeClient, "execution_status", status_404)
    # The default fake list_activities emits workflow_completed on its
    # second call, so the loop should still reach a terminal verdict.
    result = runner.invoke(cli.app, ["workflow", "run", "Catalogue", "doc-7", "--wait"])
    assert result.exit_code == 0
    # The activity log must have been polled at least twice (and won the race
    # over the 404'ing status endpoint).
    activity_polls = [c for c in _last_client().calls if c[0] == "list_activities"]
    assert len(activity_polls) >= 2
    assert "status: completed" in result.output


def test_workflow_run_wait_uses_activity_log_not_status(monkeypatch):
    """Regression for #1088: the wait loop must NOT short-circuit on the
    status endpoint reporting "completed" — that's only true between nodes
    when there are no pending writes. The terminal signal is a
    ``workflow_completed`` event in the activity log.
    """
    # Status endpoint perpetually lies that we're done.
    def always_completed(self, thread_id):
        self.calls.append(("execution_status", thread_id))
        return {"thread_id": thread_id, "status": "completed", "current_state": {}}

    activity_calls = {"count": 0}

    def slow_executor(self, *, thread_id=None, types=None, limit=100):
        self.calls.append(("list_activities", thread_id, types, limit))
        activity_calls["count"] += 1
        # Three empty polls before the executor finishes.
        if activity_calls["count"] < 4:
            return []
        return [
            {
                "id": "act-end",
                "type": "workflow_completed",
                "thread_id": thread_id,
                "workflow_id": "wf-1",
            }
        ]

    monkeypatch.setattr(FakeClient, "execution_status", always_completed)
    monkeypatch.setattr(FakeClient, "list_activities", slow_executor)
    result = runner.invoke(cli.app, ["workflow", "run", "Catalogue", "doc-7", "--wait"])
    assert result.exit_code == 0
    # The activity log must have been polled multiple times — proves we
    # didn't trust the status endpoint's premature "completed".
    assert activity_calls["count"] >= 4


def test_workflow_run_wait_propagates_non_404_errors(monkeypatch):
    """A 500 (or any non-404) during polling should bail out, not loop."""

    def boom(self, thread_id):
        self.calls.append(("execution_status", thread_id))
        raise FicheroError("kaboom", status_code=500)

    monkeypatch.setattr(FakeClient, "execution_status", boom)
    result = runner.invoke(cli.app, ["workflow", "run", "Catalogue", "doc-7", "--wait"])
    assert result.exit_code == 1
    assert "kaboom" in result.output


def test_workflow_run_wait_raises_on_timeout(monkeypatch):
    """If no terminal activity event ever appears, surface a timeout —
    do NOT return silently with empty output, which would mask the failure.

    The wait loop now keys off the activity log (#1088 fix). Simulate an
    executor that never emits ``workflow_completed`` by returning empty
    activity payloads forever, and shrink both poll-budget knobs so the
    test exits quickly.
    """

    def perma_404(self, thread_id):
        self.calls.append(("execution_status", thread_id))
        raise FicheroError("not ready", status_code=404)

    def empty_activities(self, *, thread_id=None, types=None, limit=100):
        self.calls.append(("list_activities", thread_id, types, limit))
        return []

    monkeypatch.setattr(FakeClient, "execution_status", perma_404)
    monkeypatch.setattr(FakeClient, "list_activities", empty_activities)
    # Shrink both budgets so the test is fast — wall-clock dominates with
    # zero timeout, attempt cap is the safety net.
    monkeypatch.setattr(cli, "_POLL_MAX_ATTEMPTS", 3)
    result = runner.invoke(
        cli.app,
        ["workflow", "run", "Catalogue", "doc-7", "--wait", "--timeout", "0"],
    )
    assert result.exit_code == 1
    assert "Timed out" in result.output
    assert "fichero activity" in result.output


# -- workflow run --wait #1079: workflow_id/name on terminal payload --------
def test_workflow_run_wait_resolves_workflow_id_when_status_says_unknown(monkeypatch):
    """Regression for #1079: when the status endpoint reports
    ``workflow_id: unknown`` (which it does for fast runs whose checkpoint
    metadata hasn't been hydrated), the CLI must fall back to the workflow
    id we passed to ``run_workflow``.
    """

    def status_unknown(self, thread_id):
        self.calls.append(("execution_status", thread_id))
        return {
            "thread_id": thread_id,
            "workflow_id": "unknown",
            "workflow_name": "Unknown",
            "status": "completed",
        }

    monkeypatch.setattr(FakeClient, "execution_status", status_unknown)
    result = runner.invoke(
        cli.app, ["--json", "workflow", "run", "Catalogue", "doc-7", "--wait"]
    )
    assert result.exit_code == 0
    payload = json.loads(result.output)
    # We resolved "Catalogue" -> wf-1 client-side; that id must replace
    # the placeholder so users can chain to other commands.
    assert payload["workflow_id"] == "wf-1"


# -- artifacts get ---------------------------------------------------------
def test_artifacts_get_prints_header_then_content():
    """`artifacts get <id>` shows provenance fields then a separator then content."""
    result = runner.invoke(cli.app, ["artifacts", "get", "a-99"])
    assert result.exit_code == 0
    out = result.output
    assert "id: a-99" in out
    assert "document_id: doc-7" in out
    assert "artifact_type: transcription" in out
    assert "provider/model: openai/gpt-4o" in out
    assert "version: 2" in out
    # Separator (60 dashes) and the actual content body.
    assert "-" * 60 in out
    assert "hello world" in out
    # Header must come before content — separator is the boundary.
    sep_idx = out.index("-" * 60)
    assert out.index("artifact_type") < sep_idx < out.index("hello world")
    assert ("get_artifact", "a-99") in _last_client().calls


def test_artifacts_get_json_emits_raw_model():
    """The global --json flag should emit the model dump, not the human view."""
    result = runner.invoke(cli.app, ["--json", "artifacts", "get", "a-99"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["id"] == "a-99"
    assert payload["content"] == "hello world"
    assert payload["provider"] == "openai"


def test_artifacts_list_still_works():
    """The new typer-group conversion preserves the per-doc list behaviour."""
    result = runner.invoke(cli.app, ["artifacts", "list", "doc-7"])
    assert result.exit_code == 0
    call = next(c for c in _last_client().calls if c[0] == "list_artifacts")
    assert call[1] == "doc-7"


# -- import --recursive ---------------------------------------------------
def test_import_directory_recursive(tmp_path):
    """A directory PATH should fan out into per-file imports.

    Hidden files (dot-prefixed) and hidden subdirs are skipped at every depth;
    individual successes/failures are reported per-line; a final summary line
    reports totals. Exit code stays zero unless every file failed.
    """
    (tmp_path / "a.txt").write_text("a")
    (tmp_path / "b.txt").write_text("b")
    (tmp_path / ".hidden.txt").write_text("h")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "c.txt").write_text("c")
    hidden_dir = tmp_path / ".dotdir"
    hidden_dir.mkdir()
    (hidden_dir / "x.txt").write_text("x")

    result = runner.invoke(cli.app, ["import", str(tmp_path)])
    assert result.exit_code == 0
    out = result.output
    # Three visible files were imported (recursive default for directories);
    # hidden file and hidden-dir contents are skipped.
    assert "imported a.txt -> d99" in out
    assert "imported b.txt -> d99" in out
    assert "imported c.txt -> d99" in out
    assert ".hidden.txt" not in out
    assert "x.txt" not in out
    assert "summary: 3 imported, 0 failed, 3 total" in out


def test_import_directory_no_recursive(tmp_path):
    """``--no-recursive`` keeps the import to top-level files only."""
    (tmp_path / "a.txt").write_text("a")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "c.txt").write_text("c")

    result = runner.invoke(cli.app, ["import", str(tmp_path), "--no-recursive"])
    assert result.exit_code == 0
    assert "imported a.txt" in result.output
    assert "c.txt" not in result.output
    assert "summary: 1 imported, 0 failed, 1 total" in result.output


def test_import_directory_continues_on_failure(monkeypatch, tmp_path):
    """One failure must not abort the batch — log and keep going."""
    (tmp_path / "ok.txt").write_text("o")
    (tmp_path / "bad.txt").write_text("b")

    def selective_import(self, path, parent_id=None):
        self.calls.append(("import_file", path, parent_id))
        if path.endswith("bad.txt"):
            raise FicheroError("boom")
        return {"id": "d-ok", "filename": path}

    monkeypatch.setattr(FakeClient, "import_file", selective_import)
    result = runner.invoke(cli.app, ["import", str(tmp_path)])
    assert result.exit_code == 0  # partial success is still success
    out = result.output
    assert "imported ok.txt -> d-ok" in out
    assert "failed bad.txt: boom" in out
    assert "summary: 1 imported, 1 failed, 2 total" in out


def test_import_single_file_unchanged(tmp_path):
    """Single-file calls keep the original typed-output behaviour for back-
    compat with existing scripts and the JSON contract."""
    target = tmp_path / "one.pdf"
    target.write_text("data")
    result = runner.invoke(cli.app, ["import", str(target), "--parent", "f1"])
    assert result.exit_code == 0
    # The original code path delegates to a single import_file call.
    assert ("import_file", str(target), "f1") in _last_client().calls


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


# -- library create / list -------------------------------------------------
def test_library_create_calls_client_with_expanded_path():
    """`library create ~/Foo.fichero` expands ~ before sending to client."""
    result = runner.invoke(cli.app, ["library", "create", "~/Documents/x.fichero"])
    assert result.exit_code == 0, result.output
    call = next(c for c in _last_client().calls if c[0] == "create_library")
    # ~ must be expanded — the backend allowlist works on expanded paths.
    assert not call[1].startswith("~")
    assert call[1].endswith("/Documents/x.fichero")
    assert "created: true" in result.output.lower()


def test_library_create_json_emits_typed_response():
    result = runner.invoke(
        cli.app, ["--json", "library", "create", "/var/folders/test.fichero"]
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["created"] is True
    assert payload["tables_initialized"] is True
    assert payload["path"] == "/var/folders/test.fichero"


def test_library_list_walks_filesystem(tmp_path, monkeypatch):
    """`library list` is a pure FS walk — no backend call required."""
    # Build a fake roots tuple so we don't depend on Daniel's real ~/Documents.
    fake_root = tmp_path / "Documents"
    fake_root.mkdir()
    (fake_root / "MyLib.fichero").mkdir()
    (fake_root / "Sub").mkdir()
    (fake_root / "Sub" / "Nested.fichero").mkdir()
    (fake_root / "NotALibrary").mkdir()  # no .fichero suffix → ignored

    monkeypatch.setattr(cli, "_LIBRARY_LIST_ROOTS", (fake_root,))

    result = runner.invoke(cli.app, ["library", "list"])
    assert result.exit_code == 0, result.output
    assert "MyLib.fichero" in result.output
    assert "Nested.fichero" in result.output
    assert "NotALibrary" not in result.output
    # No client should have been instantiated for `list`.
    assert FakeClient.instances == []


def test_library_list_json(tmp_path, monkeypatch):
    fake_root = tmp_path / "Documents"
    fake_root.mkdir()
    (fake_root / "A.fichero").mkdir()
    monkeypatch.setattr(cli, "_LIBRARY_LIST_ROOTS", (fake_root,))

    result = runner.invoke(cli.app, ["--json", "library", "list"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert "libraries" in payload
    assert any(p.endswith("A.fichero") for p in payload["libraries"])
