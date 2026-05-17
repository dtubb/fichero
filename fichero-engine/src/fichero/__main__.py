"""Fichero CLI — a thin command-line client for the backend.

Every command is one or two HTTP calls through FicheroClient; there is no
backend logic here. Run ``fichero --help`` for the command tree. The console
entry point ``fichero = "fichero.__main__:main"`` is declared in pyproject.toml.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable, Optional

import typer

from fichero.cli import FicheroClient, FicheroError
from fichero.cli.formatters import render

app = typer.Typer(
    add_completion=False,
    help="Fichero CLI — a thin HTTP client for the Fichero backend.",
    no_args_is_help=True,
)
docs_app = typer.Typer(help="List and inspect documents.", no_args_is_help=True)
workflow_app = typer.Typer(help="List and run workflows.", no_args_is_help=True)
threads_app = typer.Typer(help="Manage workflow execution threads.", no_args_is_help=True)
kg_app = typer.Typer(help="Query the knowledge graph.", no_args_is_help=True)
library_app = typer.Typer(
    help="Create and enumerate .fichero library packages.",
    no_args_is_help=True,
)
artifacts_app = typer.Typer(
    help="List and inspect artifacts.", no_args_is_help=True
)
claim_app = typer.Typer(help="Inspect and curate knowledge claims.", no_args_is_help=True)
entity_app = typer.Typer(help="Inspect and curate knowledge entities.", no_args_is_help=True)
audit_app = typer.Typer(help="Review entity merge/split audit trail.", no_args_is_help=True)
settings_app = typer.Typer(help="Read and write AI-defaults settings.", no_args_is_help=True)
providers_app = typer.Typer(help="Manage LLM provider configurations.", no_args_is_help=True)
app.add_typer(docs_app, name="docs")
app.add_typer(workflow_app, name="workflow")
app.add_typer(kg_app, name="kg")
app.add_typer(library_app, name="library")
app.add_typer(artifacts_app, name="artifacts")
app.add_typer(claim_app, name="claim")
app.add_typer(entity_app, name="entity")
app.add_typer(audit_app, name="audit")
app.add_typer(settings_app, name="settings")
app.add_typer(providers_app, name="providers")
workflow_app.add_typer(threads_app, name="threads")

# Execution statuses the workflow status endpoint may return when the run has
# stopped from its perspective. The status endpoint alone is unreliable
# mid-run — it reports ``completed`` whenever a checkpoint has no pending
# writes, which can happen between nodes (#1088). The wait loop below uses the
# activity log as the real signal and only falls through to the status payload
# for the workflow id/name and final state.
_TERMINAL_STATUSES = frozenset(
    {"completed", "complete", "failed", "error", "cancelled", "canceled", "done"}
)
# Activity types the executor emits when a workflow truly stops — see MEMORY:
# workflow_checkpoint_races_activity and workflows/activity.py emitters.
_TERMINAL_ACTIVITY_TYPES = (
    "workflow_completed",
    "workflow_failed",
    "workflow_cancelled",
)
_POLL_INTERVAL_SECONDS = 1.0
_DEFAULT_WAIT_TIMEOUT_SECONDS = 300.0  # 5 minutes — overridable with --timeout
# Legacy attempt cap kept for back-compat with tests that monkeypatch it
# (test_workflow_run_wait_raises_on_all_404_exhaustion). The wait loop now
# bounds itself by wall time, but honors this cap when it's been narrowed.
_POLL_MAX_ATTEMPTS = 600


@app.callback()
def _configure(
    ctx: typer.Context,
    library: Optional[str] = typer.Option(
        None,
        "--library",
        "-l",
        envvar="FICHERO_LIBRARY_PATH",
        help="Path to the .fichero library package.",
    ),
    base_url: Optional[str] = typer.Option(
        None,
        "--base-url",
        envvar="FICHERO_API_URL",
        help="Backend base URL (default: http://127.0.0.1:8765).",
    ),
    token: Optional[str] = typer.Option(
        None,
        "--token",
        envvar="FICHERO_API_KEY",
        help="Bearer auth token (default: read from the engine's key file).",
    ),
    json_output: bool = typer.Option(
        False, "--json", help="Emit raw JSON instead of human-readable text."
    ),
) -> None:
    """Shared options for every command."""
    ctx.obj = {
        "library": library,
        "base_url": base_url,
        "token": token,
        "json": json_output,
    }


def _client(ctx: typer.Context) -> FicheroClient:
    opts = ctx.obj
    return FicheroClient(
        base_url=opts["base_url"],
        library_path=opts["library"],
        token=opts["token"],
    )


def _invoke(ctx: typer.Context, operation: Callable[[FicheroClient], Any]) -> None:
    """Run one client operation, render the result, and surface errors cleanly."""
    try:
        with _client(ctx) as client:
            data = operation(client)
    except FicheroError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(render(data, as_json=ctx.obj["json"]))


# -- top-level commands ----------------------------------------------------
@app.command()
def health(ctx: typer.Context) -> None:
    """Check that the backend is up."""
    _invoke(ctx, lambda c: c.health())


def _iter_importable_files(root: Path, recursive: bool) -> list[Path]:
    """Collect files to import from ``root``.

    Skips dot-prefixed entries at every level (the ``.fichero`` package itself
    contains a ``.git``-like internal layout we never want to upload, and dot-
    files in users' Documents folders are almost always editor or OS metadata).
    For a single file we just return it. For a directory: top-level files
    only when ``recursive`` is False; full ``rglob`` when True.
    """
    if root.is_file():
        return [root]
    if not root.is_dir():
        return []

    if recursive:
        return sorted(
            p
            for p in root.rglob("*")
            if p.is_file() and not _has_hidden_part(p, root)
        )
    return sorted(
        p for p in root.iterdir() if p.is_file() and not p.name.startswith(".")
    )


def _has_hidden_part(path: Path, root: Path) -> bool:
    """True if any path segment between ``root`` and ``path`` is hidden."""
    try:
        rel = path.relative_to(root)
    except ValueError:
        return False
    return any(part.startswith(".") for part in rel.parts)


@app.command(name="import")
def import_file(
    ctx: typer.Context,
    path: str = typer.Argument(..., help="File or directory to import."),
    parent: Optional[str] = typer.Option(
        None, "--parent", help="Parent folder document ID."
    ),
    recursive: bool = typer.Option(
        True,
        "--recursive/--no-recursive",
        help=(
            "When PATH is a directory, recurse into subdirectories. Ignored "
            "when PATH is a single file. Hidden (dot-prefixed) entries are "
            "always skipped."
        ),
    ),
) -> None:
    """Import a file or directory into the library (multipart upload).

    For directories, every file is imported individually and a per-file
    success/failure line is printed. Individual failures don't abort the
    batch — a final summary line reports totals. Exit code is non-zero only
    if every file failed (so CI scripts can distinguish "partial" from
    "total failure").
    """
    target = Path(path).expanduser()

    # Single-file (or non-existent) path keeps the original typed-output
    # behavior so JSON callers and the existing test contract still pass —
    # FicheroClient.import_file raises a clean error on missing files.
    if not target.is_dir():
        _invoke(ctx, lambda c: c.import_file(str(target), parent_id=parent))
        return

    files = _iter_importable_files(target, recursive=recursive)
    if not files:
        typer.echo(f"no importable files under {target}")
        return

    succeeded: list[tuple[str, str]] = []
    failed: list[tuple[str, str]] = []
    try:
        with _client(ctx) as client:
            for file_path in files:
                try:
                    result = client.import_file(str(file_path), parent_id=parent)
                    doc_id = (
                        result.get("id")
                        if isinstance(result, dict)
                        else getattr(result, "id", "?")
                    ) or "?"
                    succeeded.append((file_path.name, str(doc_id)))
                    typer.echo(f"imported {file_path.name} -> {doc_id}")
                except FicheroError as exc:
                    failed.append((file_path.name, str(exc)))
                    typer.echo(f"failed {file_path.name}: {exc}", err=True)
    except FicheroError as exc:
        # Connection error before we even started — surface and bail.
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(
        f"summary: {len(succeeded)} imported, {len(failed)} failed, "
        f"{len(files)} total"
    )
    if failed and not succeeded:
        raise typer.Exit(code=1)


@artifacts_app.command("list")
def artifacts_list(
    ctx: typer.Context,
    doc_id: str = typer.Argument(..., help="Document ID."),
    artifact_type: Optional[str] = typer.Option(
        None, "--type", help="Filter by artifact type."
    ),
    limit: int = typer.Option(50, "--limit"),
) -> None:
    """List a document's artifacts."""
    if ctx.obj["json"]:
        _invoke(
            ctx, lambda c: c.list_artifacts(doc_id, artifact_type=artifact_type, limit=limit)
        )
        return
    try:
        with _client(ctx) as client:
            artifacts = client.list_artifacts(doc_id, artifact_type=artifact_type, limit=limit)
    except FicheroError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    from fichero.cli.formatters import render_artifact

    if isinstance(artifacts, list):
        for artifact in artifacts:
            typer.echo(render_artifact(artifact))
    else:
        typer.echo(render_artifact(artifacts))


@artifacts_app.command("get")
def artifacts_get(
    ctx: typer.Context,
    artifact_id: str = typer.Argument(..., help="Artifact ID."),
) -> None:
    """Show a single artifact — header fields, then the rendered content.

    Human output prints the provenance header (id, document_id, type,
    provider/model, version, created_at), a separator, and then the artifact's
    ``content`` text. ``--json`` (the global flag) emits the raw model.
    """
    try:
        with _client(ctx) as client:
            artifact = client.get_artifact(artifact_id)
    except FicheroError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    if ctx.obj["json"]:
        typer.echo(render(artifact, as_json=True))
        return

    provider_model = "/".join(p for p in (artifact.provider, artifact.model) if p) or "-"
    created = artifact.created_at.isoformat() if artifact.created_at else "-"
    typer.echo(f"id: {artifact.id}")
    typer.echo(f"document_id: {artifact.document_id}")
    typer.echo(f"artifact_type: {artifact.artifact_type}")
    typer.echo(f"provider/model: {provider_model}")
    typer.echo(f"version: {artifact.version}")
    typer.echo(f"created_at: {created}")
    typer.echo("-" * 60)
    typer.echo(artifact.content if artifact.content is not None else "(no content)")


# Backend accepts only these search types (#1107). `keyword` is a friendly
# alias for `fulltext` so users with that mental model don't get a 400.
_SEARCH_TYPE_CHOICES = ("semantic", "fulltext", "hybrid", "keyword")
_SEARCH_TYPE_ALIASES = {"keyword": "fulltext"}


def _validate_search_type(value: str) -> str:
    """Typer callback — accept the four choices, normalize aliases."""
    normalized = (value or "").lower()
    if normalized not in _SEARCH_TYPE_CHOICES:
        raise typer.BadParameter(
            f"'{value}' is not one of {list(_SEARCH_TYPE_CHOICES)}."
        )
    return _SEARCH_TYPE_ALIASES.get(normalized, normalized)


@app.command()
def search(
    ctx: typer.Context,
    query: str = typer.Argument(..., help="Search query."),
    limit: int = typer.Option(10, "--limit"),
    search_type: str = typer.Option(
        "hybrid",
        "--type",
        help="Search mode: [semantic | fulltext (alias: keyword) | hybrid].",
        callback=_validate_search_type,
    ),
    in_doc: Optional[str] = typer.Option(
        None, "--in-doc", help="Restrict results to this document ID."
    ),
    in_folder: Optional[str] = typer.Option(
        None, "--in-folder", help="Restrict results to this folder ID."
    ),
) -> None:
    """Search documents. Use --in-doc / --in-folder to scope results."""
    if ctx.obj["json"]:
        _invoke(
            ctx,
            lambda c: c.search(
                query,
                limit=limit,
                search_type=search_type,
                doc_id=in_doc,
                folder_id=in_folder,
            ),
        )
        return
    try:
        with _client(ctx) as client:
            data = client.search(
                query,
                limit=limit,
                search_type=search_type,
                doc_id=in_doc,
                folder_id=in_folder,
            )
    except FicheroError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    from fichero.cli.formatters import render_claim

    # Try to render as search results with custom formatting first
    results = data.get("results") if isinstance(data, dict) else data
    if isinstance(results, list) and results:
        typer.echo(f"results ({len(results)}):")
        for r in results:
            # If result has claim-like structure, use render_claim
            if isinstance(r, dict) and "subject_canonical" in r:
                typer.echo(f"  {render_claim(r)}")
            else:
                # Fall back to custom search result formatting
                typer.echo(_render_search_result_item(r))
    else:
        typer.echo(_render_search_results(data))


def _render_search_result_item(r: Any) -> str:
    """Render a single search result item — score, doc id, name, preview, highlights."""
    if not isinstance(r, dict):
        return f"  - {r}"
    score = r.get("score")
    score_str = f"{score:.3f}" if isinstance(score, (int, float)) else "  -  "
    doc_id = str(r.get("document_id") or r.get("id") or "?")
    doc_id_short = doc_id[:8]
    meta = r.get("metadata") if isinstance(r.get("metadata"), dict) else {}
    name = meta.get("name") or meta.get("title") or meta.get("filename")
    if not name:
        path = meta.get("path") or ""
        name = path.rsplit("/", 1)[-1] if path else "(unnamed)"
    preview = (r.get("content_preview") or "").strip().replace("\n", " ")
    if len(preview) > 80:
        preview = preview[:80] + "…"
    lines = [f"  {score_str}  {doc_id_short}  {name}"]
    if preview:
        lines.append(f"              {preview}")
    highlights = r.get("highlights") or []
    if isinstance(highlights, list) and highlights:
        joined = " / ".join(str(h).strip().replace("\n", " ") for h in highlights[:2])
        if len(joined) > 120:
            joined = joined[:120] + "…"
        lines.append(f"              highlights: {joined}")
    return "\n".join(lines)


def _render_search_results(data: Any) -> str:
    """Pretty-print a search response — score, doc id, name, preview, highlights.

    The default renderer would print ``- (item)`` for each result because the
    backend ``SearchResult`` shape uses ``document_id``/``content_preview`` and
    nests the human label under ``metadata.name`` — neither matches the
    renderer's ID/LABEL key lists. This bespoke formatter keeps ``--json``
    untouched (handled in ``search()``) and only changes human output. (#1106)
    """
    results = data.get("results") if isinstance(data, dict) else data
    if not isinstance(results, list) or not results:
        return "results: (empty)"
    lines = [f"results ({len(results)}):"]
    for r in results:
        lines.append(_render_search_result_item(r))
    return "\n".join(lines)


@app.command()
def activity(
    ctx: typer.Context, limit: int = typer.Option(50, "--limit")
) -> None:
    """Show recent workflow activity."""
    _invoke(ctx, lambda c: c.recent_activity(limit=limit))


# -- docs ------------------------------------------------------------------
@docs_app.command("list")
def docs_list(
    ctx: typer.Context,
    parent: Optional[str] = typer.Option(None, "--parent", help="Filter by parent ID."),
    doc_type: Optional[str] = typer.Option(None, "--doc-type"),
    file_type: Optional[str] = typer.Option(None, "--file-type"),
    status: Optional[str] = typer.Option(None, "--status"),
    limit: Optional[int] = typer.Option(None, "--limit"),
) -> None:
    """List documents."""
    if ctx.obj["json"]:
        _invoke(
            ctx,
            lambda c: c.list_documents(
                parent_id=parent,
                doc_type=doc_type,
                file_type=file_type,
                status=status,
                limit=limit,
            ),
        )
        return
    try:
        with _client(ctx) as client:
            documents = client.list_documents(
                parent_id=parent,
                doc_type=doc_type,
                file_type=file_type,
                status=status,
                limit=limit,
            )
    except FicheroError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    from fichero.cli.formatters import render_document

    if isinstance(documents, list):
        for doc in documents:
            typer.echo(render_document(doc))
    else:
        typer.echo(render_document(documents))


@docs_app.command("get")
def docs_get(
    ctx: typer.Context, doc_id: str = typer.Argument(..., help="Document ID.")
) -> None:
    """Show a single document."""
    _invoke(ctx, lambda c: c.get_document(doc_id))


# -- workflows -------------------------------------------------------------
@workflow_app.command("list")
def workflow_list(ctx: typer.Context) -> None:
    """List available workflows."""
    _invoke(ctx, lambda c: c.list_workflows())


def _resolve_workflow(client: FicheroClient, name: str) -> str:
    """Resolve a workflow name (or ID) to its ID.

    ``list_workflows()`` now returns ``list[Workflow]`` (typed Pydantic
    instances), so this matches by attribute access — not dict access.
    """
    workflows = client.list_workflows()
    needle = name.lower()
    for workflow in workflows:
        if (workflow.name or "").lower() == needle:
            return workflow.id
    for workflow in workflows:
        if workflow.id == name:
            return name
    raise FicheroError(
        f"No workflow named '{name}'. Run 'fichero workflow list' to see options."
    )


def _poll_activity_for_terminal(
    client: FicheroClient, thread_id: str
) -> dict[str, Any] | None:
    """Look in the durable activity log for a workflow-stop event for ``thread_id``.

    Returns the matching activity dict (with ``type`` in
    ``_TERMINAL_ACTIVITY_TYPES``) or ``None`` if no terminal event has been
    written yet. Connection errors are re-raised; an empty/garbled response
    is treated as "nothing yet" so transient backend hiccups don't kill the
    poll loop.
    """
    payload = client.list_activities(
        thread_id=thread_id,
        types=",".join(_TERMINAL_ACTIVITY_TYPES),
        limit=10,
    )
    if not isinstance(payload, list):
        return None
    for entry in payload:
        if isinstance(entry, dict) and entry.get("type") in _TERMINAL_ACTIVITY_TYPES:
            return entry
    return None


def _safe_status(client: FicheroClient, thread_id: str) -> Any:
    """Best-effort fetch of the status endpoint — None on 404.

    Used to enrich the wait-loop output with workflow_id / workflow_name /
    final state. Non-404 errors propagate so the CLI can surface them.
    """
    try:
        return client.execution_status(thread_id)
    except FicheroError as exc:
        if exc.status_code == 404:
            return None
        raise


def _poll_until_terminal(
    client: FicheroClient,
    thread_id: str,
    *,
    timeout_seconds: float = _DEFAULT_WAIT_TIMEOUT_SECONDS,
    fallback_workflow_id: str | None = None,
) -> Any:
    """Block until the workflow truly stops, then return a status payload.

    The status endpoint reports ``completed`` whenever a checkpoint has no
    pending writes — which is also briefly true between nodes mid-run, so
    polling it alone returns mid-execution snapshots (#1088). The activity
    log is the durable source of truth: the executor only emits a
    ``workflow_completed`` / ``workflow_failed`` / ``workflow_cancelled``
    event once the run itself has actually finished.

    Loop logic:

    * Each tick: query ``/api/activity?thread_id=&types=workflow_completed,...``.
      A hit means the run is genuinely terminal — fetch the final status
      payload and return it (with ``workflow_id`` / ``workflow_name`` filled
      from the activity event if the status endpoint still 404s, fixing
      #1079).
    * 404 from either endpoint is "not ready yet" — keep polling.
    * Any other backend error propagates immediately.
    * Bound by wall-clock ``timeout_seconds`` (CLI ``--timeout``). On timeout
      we raise FicheroError with a pointer to ``fichero activity`` so the
      caller can investigate.
    """
    deadline = time.monotonic() + max(timeout_seconds, 0.0)
    # Honour the legacy attempt cap — tests narrow it to make timeout
    # assertions fast. When the cap is at its default (600) the wall-clock
    # deadline dominates.
    attempts_remaining = _POLL_MAX_ATTEMPTS
    last_status: Any = None

    while attempts_remaining > 0 and time.monotonic() < deadline:
        attempts_remaining -= 1
        try:
            terminal_event = _poll_activity_for_terminal(client, thread_id)
        except FicheroError as exc:
            if exc.status_code == 404:
                terminal_event = None
            else:
                raise
        if terminal_event is not None:
            final_status = _safe_status(client, thread_id)
            return _merge_terminal_payload(
                thread_id=thread_id,
                terminal_event=terminal_event,
                status=final_status,
                fallback_workflow_id=fallback_workflow_id,
            )
        # Capture the latest status snapshot for diagnostics on timeout — we
        # don't trust it for completion, but it's useful in the error message.
        try:
            last_status = client.execution_status(thread_id)
        except FicheroError as exc:
            if exc.status_code != 404:
                raise
        time.sleep(_POLL_INTERVAL_SECONDS)

    raise FicheroError(
        f"Timed out after {timeout_seconds:.0f}s waiting for workflow thread "
        f"{thread_id} to emit a terminal activity event. Check "
        f"`fichero activity --limit 50` for what the executor is doing. "
        f"Last status snapshot: {last_status!r}"
    )


def _merge_terminal_payload(
    *,
    thread_id: str,
    terminal_event: dict[str, Any],
    status: Any,
    fallback_workflow_id: str | None,
) -> dict[str, Any]:
    """Assemble the user-facing payload for a finished ``--wait`` run.

    Prefer the live status endpoint (it has ``current_state`` and the canonical
    workflow name). Fall back to the activity event for ``workflow_id`` and
    derive the run-level status from the event type — which ensures
    ``failed`` / ``cancelled`` runs are reported as such even if the status
    endpoint hasn't caught up. ``workflow_id: unknown`` (#1079) is repaired
    here by falling back to the id we passed to ``run_workflow``.
    """
    event_type = str(terminal_event.get("type") or "")
    derived_status = event_type.removeprefix("workflow_") or "completed"

    base: dict[str, Any] = {}
    # status may be a typed ExecutionStatusResponse, a raw dict (FakeClient),
    # or None (404).
    from pydantic import BaseModel as _BaseModel

    if isinstance(status, _BaseModel):
        base.update(status.model_dump(mode="json"))
    elif isinstance(status, dict):
        base.update(status)

    base.setdefault("thread_id", thread_id)
    base["status"] = derived_status

    workflow_id = base.get("workflow_id")
    if workflow_id in (None, "", "unknown"):
        candidate = terminal_event.get("workflow_id") or fallback_workflow_id
        if candidate:
            base["workflow_id"] = candidate

    if not base.get("workflow_name") or base["workflow_name"] == "Unknown":
        # The activity event doesn't carry the workflow name, but if the
        # status endpoint already returned one we keep it. Otherwise leave
        # the value as-is and let the renderer show the id.
        pass

    if event_type == "workflow_failed" and not base.get("error"):
        base["error"] = terminal_event.get("error") or terminal_event.get("message")

    return base


@workflow_app.command("run")
def workflow_run(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Workflow name or ID."),
    doc_id: str = typer.Argument(..., help="Document ID to run the workflow on."),
    wait: bool = typer.Option(
        False, "--wait", help="Poll until the run completes or fails."
    ),
    timeout: float = typer.Option(
        _DEFAULT_WAIT_TIMEOUT_SECONDS,
        "--timeout",
        help="Seconds to wait for completion when --wait is set.",
    ),
) -> None:
    """Run a workflow on a document."""
    try:
        with _client(ctx) as client:
            workflow_id = _resolve_workflow(client, name)
            # SwiftUI passes the selection as `selected_doc_ids` (see
            # `Views/Workflow/WorkflowEditor+Actions.swift` and the comment
            # in `workflows/tools/sources.py::files_tool`). The execute API
            # drops `inputs` straight into the workflow state — `inputs.files`
            # only fires Priority 1 when an upstream node is mapped, which
            # CLI runs don't have. `selected_doc_ids` is the Priority 2 path
            # the Files-source node reads from state.
            result = client.run_workflow(workflow_id, {"selected_doc_ids": [doc_id]})
            # run_workflow now returns a typed ExecuteAcceptedResponse; the
            # FakeClient still hands back a raw dict, so handle both.
            if hasattr(result, "thread_id"):
                thread_id = result.thread_id
            elif isinstance(result, dict):
                thread_id = result.get("thread_id")
            else:
                thread_id = None
            if wait and thread_id:
                result = _poll_until_terminal(
                    client,
                    thread_id,
                    timeout_seconds=timeout,
                    fallback_workflow_id=workflow_id,
                )
    except FicheroError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    if ctx.obj["json"]:
        typer.echo(render(result, as_json=True))
    else:
        # Strip LangGraph implementation details from human output (#1081).
        # `--json` keeps the raw payload for diagnostics.
        typer.echo(render(_scrub_langgraph_internals(result)))


# Keys the executor exposes that aren't user-facing — see backend
# ``_is_internal_langchain_node`` in workflow runner; we filter the same set
# here on the CLI render side. (#1081, MEMORY: langgraph_node_display)
_LANGGRAPH_INTERNAL_KEYS = frozenset(
    {
        "__pregel_tasks",
        "parallel_results",
        "__interrupt__",
        "__metadata__",
    }
)


def _is_internal_langgraph_key(key: Any) -> bool:
    if not isinstance(key, str):
        return False
    if key.startswith("__"):
        return True
    if key.startswith("branch:to:"):
        return True
    return key in _LANGGRAPH_INTERNAL_KEYS


def _scrub_langgraph_internals(data: Any) -> Any:
    """Recursively drop LangGraph-internal keys from a payload.

    Operates on the typed model dump (or raw dict) returned by ``workflow run``
    and walks ``current_state`` plus any nested dicts/lists. Returns a new
    structure — the input is not mutated.
    """
    from pydantic import BaseModel

    if isinstance(data, BaseModel):
        data = data.model_dump(mode="json")
    if isinstance(data, dict):
        return {
            k: _scrub_langgraph_internals(v)
            for k, v in data.items()
            if not _is_internal_langgraph_key(k)
        }
    if isinstance(data, list):
        return [_scrub_langgraph_internals(item) for item in data]
    return data


# -- knowledge graph -------------------------------------------------------
def _entities_from_inspector(payload: Any) -> Any:
    """Pull just the ``entities`` array out of the inspector response.

    The inspector endpoint returns ``{entities, claims, artifacts, ...}``;
    a command named ``entities`` should show only entities. If the payload
    isn't a dict we trust the backend and return it untouched.
    """
    # The inspector now returns a typed DocumentInspectorResponse. Coerce to
    # dict via model_dump so this helper still works for both the typed and
    # raw-dict shapes (FakeClient in tests still returns a dict).
    from pydantic import BaseModel

    if isinstance(payload, BaseModel):
        payload = payload.model_dump(mode="json")
    if isinstance(payload, dict):
        # `or []` handles both missing key and explicit None — the inspector
        # may serialize sections as null when empty.
        return payload.get("entities") or []
    return payload


@kg_app.command("entities")
def kg_entities(
    ctx: typer.Context,
    doc_id: str = typer.Argument(
        ..., help="Document ID — entities are scoped to this document."
    ),
) -> None:
    """Show knowledge-graph entities for a document.

    Backed by ``GET /api/documents/{doc_id}/inspector`` — the same aggregate
    view the SwiftUI inspector pane uses.
    """
    _invoke(ctx, lambda c: _entities_from_inspector(c.document_inspector(doc_id)))


@kg_app.command("claims")
def kg_claims(
    ctx: typer.Context,
    doc_id: str = typer.Argument(
        ..., help="Document ID — claims are filtered to this document."
    ),
    limit: int = typer.Option(50, "--limit"),
) -> None:
    """List knowledge-graph claims sourced from a document."""
    _invoke(
        ctx,
        lambda c: c.list_claims(source_document_id=doc_id, limit=limit),
    )


@kg_app.command("search")
def kg_search(
    ctx: typer.Context,
    query: str = typer.Argument(..., help="Knowledge-graph search query."),
    limit: int = typer.Option(50, "--limit"),
) -> None:
    """Search the knowledge graph (entities, claims, notes, annotations)."""
    _invoke(ctx, lambda c: c.kg_search(query, limit=limit))


@kg_app.command("rebuild")
def kg_rebuild(
    ctx: typer.Context,
    vectors: bool = typer.Option(True, "--vectors/--no-vectors", help="Rebuild entity vector store."),
    triples: bool = typer.Option(True, "--triples/--no-triples", help="Rebuild RDF triple file."),
) -> None:
    """Rebuild derived KG stores (vectors + RDF triples) from canonical DB rows.

    Safe to run any time — idempotent. Use after pulling a new engine version
    or after a KG reset + re-extraction.
    """
    _invoke(ctx, lambda c: c.kg_rebuild(vectors=vectors, triples=triples))


@kg_app.command("reset")
def kg_reset(
    ctx: typer.Context,
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
) -> None:
    """Wipe all KG rows (entities, claims, links) so extraction can run fresh.

    Documents and artifacts are not touched. Run a Catalogue/Extract
    workflow afterwards to refill the knowledge graph.
    """
    if not yes:
        typer.confirm(
            "This will delete ALL entities, claims, and links. Continue?",
            abort=True,
        )
    _invoke(ctx, lambda c: c.kg_reset())


# -- library bootstrap -----------------------------------------------------
# Where `library list` looks for .fichero packages. Mirrors the server-side
# allowlist in fichero/api/main.py::_is_allowed_library_path — keep these in
# sync if you change the allowlist there. /var/folders is intentionally
# omitted from listing (it's a temp-dir escape hatch for tests, not a place
# users keep real libraries).
_LIBRARY_LIST_ROOTS = (
    Path.home() / "Documents",
    Path.home() / "Dropbox",
    Path.home() / "Library" / "Application Support",
)


def _discover_libraries(roots: tuple[Path, ...] | None = None) -> list[str]:
    """Walk the allowlist roots up to depth 2 and collect ``*.fichero`` paths.

    Depth cap is small on purpose — Daniel's libraries live one or two levels
    below ``~/Documents`` (or ``~/Dropbox``), and an unbounded walk over
    ``~/Library/Application Support`` is slow and pulls in noise we don't
    care about.

    ``roots`` defaults to ``_LIBRARY_LIST_ROOTS`` resolved at call time (not
    at function definition) so tests can ``monkeypatch.setattr(cli,
    "_LIBRARY_LIST_ROOTS", ...)`` and have it take effect.
    """
    if roots is None:
        roots = _LIBRARY_LIST_ROOTS
    found: list[str] = []
    for root in roots:
        if not root.exists():
            continue
        # Depth 0: the root itself never matches (no .fichero suffix).
        # Depth 1: ~/Documents/Foo.fichero
        # Depth 2: ~/Documents/SomeFolder/Foo.fichero
        for entry in root.iterdir():
            try:
                if entry.is_dir() and entry.suffix == ".fichero":
                    found.append(str(entry.resolve()))
                elif entry.is_dir():
                    for sub in entry.iterdir():
                        if sub.is_dir() and sub.suffix == ".fichero":
                            found.append(str(sub.resolve()))
            except OSError:
                # Permission denied / broken symlink — skip and keep going.
                continue
    # De-dup (resolved paths can collide across roots via symlinks) and sort
    # for deterministic output.
    return sorted(set(found))


@library_app.command("list")
def library_list(ctx: typer.Context) -> None:
    """List all known libraries in the registry.

    Shows libraries sorted by last_accessed (most recent first).
    Output: "path [last_accessed]" per library, or "(no libraries)" if empty.
    """

    def op(c: FicheroClient) -> Any:
        response = c.list_known_libraries()
        if not response.libraries:
            return "(no libraries)"
        return response.libraries

    _invoke(ctx, op)


@library_app.command("add")
def library_add(
    ctx: typer.Context,
    path: str = typer.Argument(
        ...,
        help="Path to the .fichero library package to register.",
    ),
) -> None:
    """Register an existing library path.

    Validates that the path exists and contains a .fichero package.
    Output: "Added: {path}"
    """
    expanded = str(Path(path).expanduser())

    def op(c: FicheroClient) -> dict:
        lib = c.add_known_library(expanded)
        return {"status": f"Added: {lib.path}"}

    _invoke(ctx, op)


@library_app.command("remove")
def library_remove(
    ctx: typer.Context,
    path: str = typer.Argument(
        ...,
        help="Path to the library to unregister.",
    ),
) -> None:
    """Unregister a library from the registry.

    Output: "Removed: {path}"
    """
    expanded = str(Path(path).expanduser())

    def op(c: FicheroClient) -> dict:
        c.remove_known_library(expanded)
        return {"status": f"Removed: {expanded}"}

    _invoke(ctx, op)


@library_app.command("create")
def library_create(
    ctx: typer.Context,
    path: str = typer.Argument(
        ...,
        help="Path to the .fichero package to create (e.g. ~/Documents/Test.fichero).",
    ),
) -> None:
    """Create a new library at path and auto-register it.

    Output: "Created and registered: {path}"
    """
    expanded = str(Path(path).expanduser())

    def op(c: FicheroClient) -> dict:
        c.create_library(expanded)
        # Auto-register by calling add_known_library
        c.add_known_library(expanded)
        return {"status": f"Created and registered: {expanded}"}

    _invoke(ctx, op)


@library_app.command("delete")
def library_delete(
    ctx: typer.Context,
    path: str = typer.Argument(
        ...,
        help="Path to the library to delete.",
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
) -> None:
    """Delete a library and remove it from the registry.

    Removes the .fichero directory from the filesystem.
    Confirm before deletion: "Delete {path}? (y/n)"
    Output: "Deleted: {path}"
    """
    expanded = str(Path(path).expanduser())

    if not yes:
        typer.confirm(f"Delete {expanded}?", abort=True)

    def op(c: FicheroClient) -> dict:
        # Remove from registry first
        c.remove_known_library(expanded)
        # Then delete the filesystem directory
        lib_path = Path(expanded)
        if lib_path.exists():
            import shutil

            shutil.rmtree(lib_path)
        return {"status": f"Deleted: {expanded}"}

    _invoke(ctx, op)


@library_app.command("open")
def library_open(
    ctx: typer.Context,
    path: str = typer.Argument(
        ...,
        help="Path to the library to activate.",
    ),
) -> None:
    """Mark library as active (updates last_accessed).

    For future: CLI will use this to switch active library context.
    Output: "Activated: {path}"
    """
    expanded = str(Path(path).expanduser())

    def op(c: FicheroClient) -> dict:
        c.update_library_access(expanded)
        return {"status": f"Activated: {expanded}"}

    _invoke(ctx, op)


@library_app.command("close")
def library_close(
    ctx: typer.Context,
    path: str = typer.Argument(
        ...,
        help="Path to the library to deactivate.",
    ),
) -> None:
    """Deactivate a library (placeholder for future logic).

    Output: "Closed: {path}"
    """
    expanded = str(Path(path).expanduser())
    # For now, this is a no-op that just prints the message
    typer.echo(f"Closed: {expanded}")


@library_app.command("reset")
def library_reset(
    ctx: typer.Context,
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
) -> None:
    """Clear all registry entries.

    Confirm before reset: "Clear all known libraries? (y/n)"
    Output: "Reset complete"
    """
    if not yes:
        typer.confirm("Clear all known libraries?", abort=True)

    def op(c: FicheroClient) -> dict:
        response = c.list_known_libraries()
        for lib in response.libraries:
            c.remove_known_library(lib.path)
        return {"status": "Reset complete"}

    _invoke(ctx, op)


# -- docs (extended) -------------------------------------------------------
@docs_app.command("delete")
def docs_delete(
    ctx: typer.Context,
    doc_id: str = typer.Argument(..., help="Document ID to delete."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
) -> None:
    """Delete a document (and cascade-delete its KG rows)."""
    if not yes:
        typer.confirm(f"Delete document {doc_id}?", abort=True)
    _invoke(ctx, lambda c: c.delete_document(doc_id))


@docs_app.command("update")
def docs_update(
    ctx: typer.Context,
    doc_id: str = typer.Argument(..., help="Document ID."),
    name: Optional[str] = typer.Option(None, "--name", help="New document name."),
    parent_id: Optional[str] = typer.Option(None, "--parent-id", help="New parent folder ID."),
    folder_path: Optional[str] = typer.Option(None, "--folder-path", help="New folder path."),
) -> None:
    """Update editable fields on a document."""
    fields: dict[str, Any] = {}
    if name is not None:
        fields["name"] = name
    if parent_id is not None:
        fields["parent_id"] = parent_id
    if folder_path is not None:
        fields["folder_path"] = folder_path
    if not fields:
        typer.secho("No fields to update — pass --name, --parent-id, or --folder-path.", err=True)
        raise typer.Exit(code=1)
    _invoke(ctx, lambda c: c.update_document(doc_id, **fields))


@docs_app.command("import")
def docs_import(
    ctx: typer.Context,
    path: Path = typer.Argument(..., help="File path to import into the library."),
    parent_id: Optional[str] = typer.Option(None, "--parent-id", help="Parent folder document ID."),
) -> None:
    """Import a file into the library (copies it in, creates a document record).

    Equivalent to drag-dropping a file in the SwiftUI app.
    """
    if not path.exists():
        typer.secho(f"File not found: {path}", err=True)
        raise typer.Exit(code=1)
    _invoke(ctx, lambda c: c.import_document(path, parent_id=parent_id))


@docs_app.command("inspector")
def docs_inspector(
    ctx: typer.Context,
    doc_id: str = typer.Argument(..., help="Document ID."),
) -> None:
    """Show the inspector aggregate view for a document."""
    _invoke(ctx, lambda c: c.document_inspector(doc_id))


@docs_app.command("kg")
def docs_kg(
    ctx: typer.Context,
    doc_id: str = typer.Argument(..., help="Document ID."),
    include_children: bool = typer.Option(
        False, "--include-children", help="Include child page documents."
    ),
) -> None:
    """Show the deduped knowledge graph for a document."""
    _invoke(
        ctx,
        lambda c: c.document_knowledge_graph(doc_id, include_children=include_children),
    )


# -- artifacts (extended) --------------------------------------------------
@artifacts_app.command("update")
def artifacts_update(
    ctx: typer.Context,
    artifact_id: str = typer.Argument(..., help="Artifact ID."),
    content: Optional[str] = typer.Option(None, "--content", help="New artifact content."),
    reviewed: Optional[bool] = typer.Option(None, "--reviewed/--not-reviewed", help="Mark as reviewed."),
) -> None:
    """Update an artifact's content and/or reviewed flag."""
    if content is None and reviewed is None:
        typer.secho("Pass --content and/or --reviewed/--not-reviewed.", err=True)
        raise typer.Exit(code=1)
    _invoke(ctx, lambda c: c.update_artifact(artifact_id, content=content, reviewed=reviewed))


@artifacts_app.command("delete")
def artifacts_delete(
    ctx: typer.Context,
    artifact_id: str = typer.Argument(..., help="Artifact ID to delete."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
) -> None:
    """Delete an artifact."""
    if not yes:
        typer.confirm(f"Delete artifact {artifact_id}?", abort=True)
    _invoke(ctx, lambda c: c.delete_artifact(artifact_id))


# -- claim -----------------------------------------------------------------
@claim_app.command("create")
def claim_create(
    ctx: typer.Context,
    text: str = typer.Argument(..., help="Claim statement text."),
    doc_id: Optional[str] = typer.Option(None, "--doc-id", help="Source document ID (omit for manual claims)."),
    entity: list[str] = typer.Option([], "--entity", "-e", help="Entity ID to associate (repeat for multiple)."),
    predicate: Optional[str] = typer.Option(None, "--predicate", help="Predicate verb (e.g. 'founded')."),
    subject: Optional[str] = typer.Option(None, "--subject", help="Subject canonical name."),
    obj: Optional[str] = typer.Option(None, "--object", help="Object phrase."),
    confidence: float = typer.Option(1.0, "--confidence", help="Confidence [0..1], default 1.0 for manual."),
) -> None:
    """Manually assert a knowledge claim (not extracted from a document).

    Use --doc-id to anchor the claim to a source document, or omit it
    for a claim asserted from your own knowledge.
    """
    _invoke(
        ctx,
        lambda c: c.create_claim(
            text,
            source_document_id=doc_id,
            entity_ids=list(entity) or None,
            predicate_verb=predicate,
            subject_canonical=subject,
            object_phrase=obj,
            confidence=confidence,
        ),
    )


@claim_app.command("get")
def claim_get(
    ctx: typer.Context,
    claim_id: str = typer.Argument(..., help="Claim ID."),
) -> None:
    """Show a single knowledge claim."""
    _invoke(ctx, lambda c: c.get_claim(claim_id))


@claim_app.command("update")
def claim_update(
    ctx: typer.Context,
    claim_id: str = typer.Argument(..., help="Claim ID."),
    text: Optional[str] = typer.Option(None, "--text", help="New claim text."),
    confidence: Optional[float] = typer.Option(None, "--confidence", help="Confidence [0..1]."),
    curation_state: Optional[str] = typer.Option(
        None, "--curation-state", help="approved | rejected | unreviewed"
    ),
) -> None:
    """Update editable fields on a knowledge claim."""
    fields: dict[str, Any] = {}
    if text is not None:
        fields["text"] = text
    if confidence is not None:
        fields["confidence"] = confidence
    if curation_state is not None:
        fields["curation_state"] = curation_state
    if not fields:
        typer.secho("Pass at least one of --text, --confidence, --curation-state.", err=True)
        raise typer.Exit(code=1)
    _invoke(ctx, lambda c: c.update_claim(claim_id, **fields))


@claim_app.command("delete")
def claim_delete(
    ctx: typer.Context,
    claim_id: str = typer.Argument(..., help="Claim ID to delete."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
) -> None:
    """Delete a knowledge claim."""
    if not yes:
        typer.confirm(f"Delete claim {claim_id}?", abort=True)
    _invoke(ctx, lambda c: c.delete_claim(claim_id))


@claim_app.command("review")
def claim_review(
    ctx: typer.Context,
    claim_id: str = typer.Argument(..., help="Claim ID."),
    status: str = typer.Option(
        ..., "--status", help="Curation status: approved | rejected | unreviewed"
    ),
) -> None:
    """Set the curation_state on a claim (approved / rejected / unreviewed)."""
    _invoke(ctx, lambda c: c.review_claim(claim_id, status=status))


@claim_app.command("list")
def claim_list(
    ctx: typer.Context,
    doc_id: Optional[str] = typer.Option(
        None, "--doc", help="Filter claims to this document ID."
    ),
    limit: int = typer.Option(50, "--limit"),
) -> None:
    """List knowledge claims, optionally filtered to a document."""
    if ctx.obj["json"]:
        _invoke(
            ctx,
            lambda c: c.list_claims(source_document_id=doc_id, limit=limit),
        )
        return
    try:
        with _client(ctx) as client:
            claims = client.list_claims(source_document_id=doc_id, limit=limit)
    except FicheroError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    from fichero.cli.formatters import render_claim

    if isinstance(claims, list):
        for claim in claims:
            typer.echo(render_claim(claim))
    else:
        typer.echo(render_claim(claims))


# -- entity ----------------------------------------------------------------
@entity_app.command("create")
def entity_create(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Canonical name for the entity."),
    entity_type: str = typer.Option("other", "--type", "-t", help="Entity type (person, place, org, concept, event, other)."),
    description: Optional[str] = typer.Option(None, "--description", "-d", help="Short description."),
    alias: list[str] = typer.Option([], "--alias", "-a", help="Alias (repeat for multiple)."),
) -> None:
    """Manually add a knowledge entity to the graph.

    Use this to assert entities that weren't extracted from a document —
    domain knowledge, corrections, or seed data for a new library.
    """
    _invoke(
        ctx,
        lambda c: c.create_entity(
            name,
            entity_type,
            description=description,
            aliases=list(alias) or None,
        ),
    )


@entity_app.command("get")
def entity_get(
    ctx: typer.Context,
    entity_id: str = typer.Argument(..., help="Entity ID."),
) -> None:
    """Show a single knowledge entity."""
    if ctx.obj["json"]:
        _invoke(ctx, lambda c: c.get_entity(entity_id))
        return
    try:
        with _client(ctx) as client:
            entity = client.get_entity(entity_id)
    except FicheroError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    from fichero.cli.formatters import render_entity

    typer.echo(render_entity(entity))


@entity_app.command("update")
def entity_update(
    ctx: typer.Context,
    entity_id: str = typer.Argument(..., help="Entity ID."),
    canonical_name: Optional[str] = typer.Option(None, "--name", help="New canonical name."),
    description: Optional[str] = typer.Option(None, "--description", help="New description."),
    entity_type: Optional[str] = typer.Option(None, "--type", help="Entity type."),
) -> None:
    """Update editable fields on a knowledge entity."""
    fields: dict[str, Any] = {}
    if canonical_name is not None:
        fields["canonical_name"] = canonical_name
    if description is not None:
        fields["description"] = description
    if entity_type is not None:
        fields["entity_type"] = entity_type
    if not fields:
        typer.secho("Pass at least one of --name, --description, --type.", err=True)
        raise typer.Exit(code=1)
    _invoke(ctx, lambda c: c.update_entity(entity_id, **fields))


@entity_app.command("delete")
def entity_delete(
    ctx: typer.Context,
    entity_id: str = typer.Argument(..., help="Entity ID to delete."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
) -> None:
    """Delete a knowledge entity."""
    if not yes:
        typer.confirm(f"Delete entity {entity_id}?", abort=True)
    _invoke(ctx, lambda c: c.delete_entity(entity_id))


@entity_app.command("merge")
def entity_merge(
    ctx: typer.Context,
    absorbing_id: str = typer.Argument(..., help="Entity ID that absorbs the others (survivor)."),
    absorbed_ids: list[str] = typer.Argument(..., help="Entity IDs to be absorbed."),
    description: Optional[str] = typer.Option(None, "--description", help="Override description."),
) -> None:
    """Merge one or more entities into an absorbing entity (creates audit record)."""
    _invoke(
        ctx,
        lambda c: c.merge_entities(
            absorbing_id, absorbed_ids, merged_description=description
        ),
    )


@entity_app.command("split")
def entity_split(
    ctx: typer.Context,
    primary_id: str = typer.Argument(..., help="Entity that retains canonical identity."),
    split_off_ids: list[str] = typer.Argument(..., help="Entity IDs to split off."),
) -> None:
    """Split off sub-entities from a primary entity (creates audit record)."""
    _invoke(
        ctx,
        lambda c: c.split_entity(primary_id, split_off_ids),
    )


@entity_app.command("top")
def entity_top(
    ctx: typer.Context,
    limit: int = typer.Option(30, "--limit", help="Number of top entities to return."),
) -> None:
    """Top-N entities by claim count across the library."""
    if ctx.obj["json"]:
        _invoke(ctx, lambda c: c.top_entities(limit=limit))
        return
    try:
        with _client(ctx) as client:
            entities = client.top_entities(limit=limit)
    except FicheroError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    from fichero.cli.formatters import render_entity

    if isinstance(entities, list):
        for entity in entities:
            typer.echo(render_entity(entity))
    else:
        typer.echo(render_entity(entities))


@entity_app.command("documents")
def entity_documents(
    ctx: typer.Context,
    entity_id: str = typer.Argument(..., help="Entity ID."),
) -> None:
    """Documents that mention this entity via knowledge claims."""
    _invoke(ctx, lambda c: c.entity_documents(entity_id))


@entity_app.command("co-occurrence")
def entity_co_occurrence(
    ctx: typer.Context,
    entity_id: str = typer.Argument(..., help="Entity ID."),
) -> None:
    """Entities that co-occur with this entity in at least one claim."""
    _invoke(ctx, lambda c: c.entity_co_occurrence(entity_id))


@entity_app.command("resolve")
def entity_resolve(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Name or alias to resolve."),
) -> None:
    """Resolve a name or alias to a canonical entity."""
    _invoke(ctx, lambda c: c.resolve_entity(name))


# -- #1125 scoped KG exploration ------------------------------------------
# These compose existing endpoints client-side to answer "entities at
# this scope" and "claims at this scope mentioning entity X". No new
# backend routes — pure CLI orchestration over list_claims +
# list_documents + entity_documents.

@entity_app.command("at-page")
def entity_at_page(
    ctx: typer.Context,
    page_doc_id: str = typer.Argument(..., help="Page document ID."),
    entity_type: Optional[str] = typer.Option(
        None, "--type", help="Filter by entity type (person/location/etc.)",
    ),
) -> None:
    """Entities mentioned on a single page."""
    _invoke(
        ctx,
        lambda c: c.entities_at_doc(page_doc_id, entity_type=entity_type),
    )


@entity_app.command("at-doc")
def entity_at_doc(
    ctx: typer.Context,
    doc_id: str = typer.Argument(
        ..., help="Document ID (a multi-page PDF or a single file).",
    ),
    entity_type: Optional[str] = typer.Option(
        None, "--type", help="Filter by entity type (person/location/etc.)",
    ),
) -> None:
    """Entities mentioned anywhere in this document (across all pages)."""
    _invoke(
        ctx,
        lambda c: c.entities_at_doc(doc_id, entity_type=entity_type),
    )


@entity_app.command("at-folder")
def entity_at_folder(
    ctx: typer.Context,
    folder_id: str = typer.Argument(..., help="Folder document ID."),
    entity_type: Optional[str] = typer.Option(
        None, "--type", help="Filter by entity type (person/location/etc.)",
    ),
    non_recursive: bool = typer.Option(
        False, "--non-recursive",
        help="Only direct children; don't walk sub-folders.",
    ),
) -> None:
    """Entities mentioned in any document under this folder.

    Recursive by default — walks every descendant. Pass
    ``--non-recursive`` to limit to direct children.
    """
    _invoke(
        ctx,
        lambda c: c.entities_at_folder(
            folder_id, recursive=not non_recursive,
            entity_type=entity_type,
        ),
    )


@entity_app.command("context")
def entity_context(
    ctx: typer.Context,
    entity_id: str = typer.Argument(..., help="Entity ID."),
) -> None:
    """Show where an entity appears: page / doc / folder counts and
    total claims. The cheap summary that drives 'navigate to this
    scope' decisions: 'Pedro Pérez appears in 12 pages across 3 docs
    in 1 folder, with 47 claims.'
    """
    _invoke(ctx, lambda c: c.entity_context(entity_id))


@entity_app.command("similar")
def entity_similar(
    ctx: typer.Context,
    entity_id: str = typer.Argument(..., help="Entity ID."),
    hops: int = typer.Option(1, "--hops", help="Graph hops to traverse (1-3)."),
    limit: int = typer.Option(20, "--limit"),
    rank: str = typer.Option(
        "edge_weight",
        "--rank",
        help="Rank neighbours by: edge_weight | degree | name.",
    ),
) -> None:
    """Show entities neighbouring this one in the knowledge graph (co-claim
    graph traversal). Use this to find related names, themes, or people that
    appear alongside the focus entity.
    """
    if ctx.obj["json"]:
        _invoke(
            ctx,
            lambda c: c.entity_neighborhood(entity_id, hops=hops, limit=limit, rank=rank),
        )
        return
    try:
        with _client(ctx) as client:
            data = client.entity_neighborhood(entity_id, hops=hops, limit=limit, rank=rank)
    except FicheroError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    focus = data.get("focus") if isinstance(data, dict) else {}
    neighbors = data.get("neighbors") if isinstance(data, dict) else []
    typer.echo(f"focus: {focus.get('canonical_name', entity_id)} ({entity_id[:8]})")
    typer.echo(f"neighbours ({len(neighbors)}):")
    for n in neighbors[:limit]:
        if not isinstance(n, dict):
            typer.echo(f"  {n}")
            continue
        nid = str(n.get("entity_id") or n.get("id") or "?")[:8]
        name = n.get("canonical_name") or n.get("name") or nid
        etype = n.get("entity_type") or ""
        weight = n.get("edge_weight") or n.get("weight")
        w_str = f"  w={weight:.2f}" if isinstance(weight, (int, float)) else ""
        typer.echo(f"  {nid}  {name:<30}  {etype}{w_str}")


@claim_app.command("at-page")
def claim_at_page(
    ctx: typer.Context,
    page_doc_id: str = typer.Argument(..., help="Page document ID."),
    entity_id: Optional[str] = typer.Option(
        None, "--entity", help="Filter to claims mentioning this entity.",
    ),
) -> None:
    """Claims sourced from this page (optionally about one entity)."""
    if ctx.obj["json"]:
        _invoke(
            ctx,
            lambda c: c.claims_at_doc(page_doc_id, entity_id=entity_id),
        )
        return
    try:
        with _client(ctx) as client:
            claims = client.claims_at_doc(page_doc_id, entity_id=entity_id)
    except FicheroError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    from fichero.cli.formatters import render_claim

    if isinstance(claims, list):
        for claim in claims:
            typer.echo(render_claim(claim))
    else:
        typer.echo(render_claim(claims))


@claim_app.command("at-doc")
def claim_at_doc(
    ctx: typer.Context,
    doc_id: str = typer.Argument(..., help="Document ID."),
    entity_id: Optional[str] = typer.Option(
        None, "--entity", help="Filter to claims mentioning this entity.",
    ),
) -> None:
    """Claims sourced from this doc or any of its pages, optionally
    about one entity."""
    if ctx.obj["json"]:
        _invoke(
            ctx,
            lambda c: c.claims_at_doc(doc_id, entity_id=entity_id),
        )
        return
    try:
        with _client(ctx) as client:
            claims = client.claims_at_doc(doc_id, entity_id=entity_id)
    except FicheroError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    from fichero.cli.formatters import render_claim

    if isinstance(claims, list):
        for claim in claims:
            typer.echo(render_claim(claim))
    else:
        typer.echo(render_claim(claims))


@claim_app.command("at-folder")
def claim_at_folder(
    ctx: typer.Context,
    folder_id: str = typer.Argument(..., help="Folder document ID."),
    entity_id: Optional[str] = typer.Option(
        None, "--entity", help="Filter to claims mentioning this entity.",
    ),
    non_recursive: bool = typer.Option(
        False, "--non-recursive",
        help="Only direct children; don't walk sub-folders.",
    ),
) -> None:
    """Claims sourced from anywhere under this folder, optionally
    about one entity."""
    if ctx.obj["json"]:
        _invoke(
            ctx,
            lambda c: c.claims_at_folder(
                folder_id,
                entity_id=entity_id,
                recursive=not non_recursive,
            ),
        )
        return
    try:
        with _client(ctx) as client:
            claims = client.claims_at_folder(
                folder_id,
                entity_id=entity_id,
                recursive=not non_recursive,
            )
    except FicheroError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    from fichero.cli.formatters import render_claim

    if isinstance(claims, list):
        for claim in claims:
            typer.echo(render_claim(claim))
    else:
        typer.echo(render_claim(claims))


# -- audit -----------------------------------------------------------------
@audit_app.command("list")
def audit_list(
    ctx: typer.Context,
    limit: int = typer.Option(50, "--limit"),
) -> None:
    """List entity merge/split audit records."""
    _invoke(ctx, lambda c: c.list_audits(limit=limit))


@audit_app.command("undo")
def audit_undo(
    ctx: typer.Context,
    audit_id: str = typer.Argument(..., help="Audit record ID to reverse."),
) -> None:
    """Reverse a merge or split operation by audit ID."""
    _invoke(ctx, lambda c: c.undo_audit(audit_id))


# -- workflow threads (extended) -------------------------------------------
@threads_app.command("list")
def threads_list(
    ctx: typer.Context,
    limit: int = typer.Option(100, "--limit"),
) -> None:
    """List recent workflow execution threads."""
    _invoke(ctx, lambda c: c.list_threads(limit=limit))


@threads_app.command("delete")
def threads_delete(
    ctx: typer.Context,
    thread_id: str = typer.Argument(..., help="Thread ID to delete."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
) -> None:
    """Delete a workflow execution thread and its checkpoints."""
    if not yes:
        typer.confirm(f"Delete thread {thread_id}?", abort=True)
    _invoke(ctx, lambda c: c.delete_thread(thread_id))


@workflow_app.command("status")
def workflow_status(
    ctx: typer.Context,
    thread_id: str = typer.Argument(..., help="Thread ID to inspect."),
) -> None:
    """Show the current status of a workflow execution thread."""
    _invoke(ctx, lambda c: c.execution_status(thread_id))


@workflow_app.command("stop")
def workflow_stop(
    ctx: typer.Context,
    thread_id: str = typer.Argument(..., help="Thread ID to cancel."),
) -> None:
    """Cancel a running workflow (#1127).

    Signals the workflow to stop at the next execution tick. Partial
    results — artifacts, entities, claims already written — are
    preserved so the comparison loop can inspect them. The response
    surfaces `status=cancel_requested|not_running|already_terminal`
    so scripts can branch on the outcome.
    """
    _invoke(ctx, lambda c: c.cancel_workflow(thread_id))


# -- settings --------------------------------------------------------------
@settings_app.command("list")
def settings_list(ctx: typer.Context) -> None:
    """Show all AI-default settings."""
    _invoke(ctx, lambda c: c.get_settings())


@settings_app.command("get")
def settings_get(
    ctx: typer.Context,
    key: str = typer.Argument(..., help="Setting key (e.g. text_model)."),
) -> None:
    """Get a single AI-default setting value."""
    try:
        with _client(ctx) as client:
            data = client.get_settings()
    except FicheroError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    value = data.get(key) if isinstance(data, dict) else None
    if value is None:
        typer.secho(f"Key '{key}' not found.", err=True)
        raise typer.Exit(code=1)
    if ctx.obj["json"]:
        typer.echo(render({key: value}, as_json=True))
    else:
        typer.echo(f"{key}: {value}")


@settings_app.command("set")
def settings_set(
    ctx: typer.Context,
    key: str = typer.Argument(..., help="Setting key (e.g. text_model)."),
    value: str = typer.Argument(..., help="Setting value."),
) -> None:
    """Set a single AI-default setting value."""
    _invoke(ctx, lambda c: c.set_settings(**{key: value}))


# -- providers -------------------------------------------------------------
@providers_app.command("list")
def providers_list(ctx: typer.Context) -> None:
    """List configured LLM providers."""
    _invoke(ctx, lambda c: c.list_providers())


@providers_app.command("get")
def providers_get(
    ctx: typer.Context,
    provider_id: str = typer.Argument(..., help="Provider ID."),
) -> None:
    """Show a single configured provider."""
    _invoke(ctx, lambda c: c.get_provider(provider_id))


@providers_app.command("add")
def providers_add(
    ctx: typer.Context,
    provider_type: str = typer.Option(..., "--type", help="Provider type (e.g. openai, anthropic)."),
    name: Optional[str] = typer.Option(None, "--name", help="Custom display name."),
    api_base: Optional[str] = typer.Option(None, "--api-base", help="Custom base URL."),
    api_key: Optional[str] = typer.Option(None, "--api-key", help="API key (stored in keychain)."),
) -> None:
    """Add or upsert a provider configuration."""
    _invoke(
        ctx,
        lambda c: c.add_provider(
            provider_type, name=name, api_base=api_base, api_key=api_key
        ),
    )


@providers_app.command("delete")
def providers_delete(
    ctx: typer.Context,
    provider_id: str = typer.Argument(..., help="Provider ID to delete."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
) -> None:
    """Delete a provider configuration."""
    if not yes:
        typer.confirm(f"Delete provider {provider_id}?", abort=True)
    _invoke(ctx, lambda c: c.delete_provider(provider_id))


@app.command()
def check(ctx: typer.Context) -> None:
    """Probe every endpoint group and report which are reachable.

    Run this after upgrading the backend to detect CLI / backend drift:
    a 404 on a previously-working route means the backend route moved or
    was renamed. A TypeError on a response field means the schema changed.

    Exit code 0 = all probes pass. Exit code 1 = one or more failures.
    """
    c = _client(ctx)

    # Each probe: (label, callable). Callable returns a truthy value or raises.
    def _probe_health():
        r = c.request("GET", "/api/health")
        assert isinstance(r, dict) and r.get("status") == "healthy"

    def _probe_docs():
        r = c.request("GET", "/api/documents", params={"limit": 1})
        assert isinstance(r, list)

    def _probe_workflows():
        r = c.request("GET", "/api/workflows", params={"limit": 1})
        assert isinstance(r, list)

    def _probe_search():
        r = c.request("POST", "/api/search", json={"query": "", "limit": 1, "min_score": 0.0})
        assert isinstance(r, dict) and "results" in r

    def _probe_activity():
        r = c.request("GET", "/api/activity", params={"limit": 1})
        assert isinstance(r, (list, dict))

    def _probe_entities():
        r = c.request("GET", "/api/entities/top", params={"limit": 1})
        assert isinstance(r, list)

    def _probe_kg_search():
        r = c.request("GET", "/api/kg/search", params={"q": "test", "limit": 1})
        assert isinstance(r, (list, dict))

    def _probe_settings():
        r = c.request("GET", "/api/settings/ai-defaults")
        assert isinstance(r, dict) and "small_provider" in r

    def _probe_providers():
        r = c.request("GET", "/api/providers")
        assert isinstance(r, list)

    def _probe_search_stats():
        r = c.request("GET", "/api/search/stats")
        assert isinstance(r, dict)

    def _probe_kg_communities():
        r = c.request("GET", "/api/kg/graph/communities", params={"limit": 1})
        assert isinstance(r, (list, dict))

    def _probe_audit():
        r = c.request("GET", "/api/kg/entity-curation/audit", params={"limit": 1})
        assert isinstance(r, (list, dict))

    def _probe_openapi():
        r = c.request("GET", "/openapi.json")
        assert isinstance(r, dict) and "paths" in r
        return r  # returned for drift check below

    probes: list[tuple[str, object]] = [
        ("health            GET /api/health", _probe_health),
        ("docs              GET /api/documents", _probe_docs),
        ("workflows         GET /api/workflows", _probe_workflows),
        ("search            POST /api/search", _probe_search),
        ("search stats      GET /api/search/stats", _probe_search_stats),
        ("activity          GET /api/activity", _probe_activity),
        ("entity top        GET /api/entities/top", _probe_entities),
        ("kg search         GET /api/kg/search", _probe_kg_search),
        ("kg communities    GET /api/kg/graph/communities", _probe_kg_communities),
        ("settings          GET /api/settings/ai-defaults", _probe_settings),
        ("providers         GET /api/providers", _probe_providers),
        ("audit log         GET /api/kg/entity-curation/audit", _probe_audit),
        ("openapi schema    GET /openapi.json", _probe_openapi),
    ]

    passed = 0
    failed = 0
    openapi_schema = None

    for label, probe_fn in probes:
        try:
            result = probe_fn()  # type: ignore[operator]
            if label.startswith("openapi"):
                openapi_schema = result
            typer.echo(f"  \033[32m✓\033[0m  {label}")
            passed += 1
        except Exception as exc:
            typer.echo(f"  \033[31m✗\033[0m  {label}  — {type(exc).__name__}: {exc}")
            failed += 1

    # Drift check: compare CLI-known routes against backend OpenAPI paths.
    # Routes present in OpenAPI but never called by any CLI probe are flagged
    # as potential CLI gaps (the CLI may be missing coverage).
    cli_paths = {
        "/api/health", "/api/documents", "/api/workflows", "/api/search",
        "/api/search/stats", "/api/activity", "/api/entities/top",
        "/api/entities", "/api/kg/search", "/api/kg/graph/communities",
        "/api/kg/graph/neighborhood/{entity_id}", "/api/kg/sparql",
        "/api/settings/ai-defaults", "/api/providers", "/api/artifacts",
        "/api/kg/entity-curation/audit",
    }
    if openapi_schema:
        backend_paths: set[str] = set(openapi_schema.get("paths", {}).keys())
        uncovered = sorted(
            p for p in backend_paths
            if p not in cli_paths
            and not p.startswith("/api/search/views")
            and not p.startswith("/api/search/saved")
            and not p.startswith("/api/kg/interpretations")
            and not p.startswith("/api/classifications")
            and not p.startswith("/api/mind-palace")
            and not p.startswith("/api/chat")
            and not p.startswith("/api/notes")
            and not p.startswith("/api/projects")
            and not p.startswith("/api/research")
            and not p.startswith("/api/ingest")
            and not p.startswith("/api/actions")
            and not p.startswith("/api/mcp")
            and not p.startswith("/api/multilingual")
            and not p.startswith("/api/folders")
            and not p.startswith("/api/integrations")
            and not p.startswith("/api/embeddings")
            and not p.startswith("/api/workflows/execute")
            and not p.startswith("/api/workflows/stream")
            and not p.startswith("/api/workflows/threads")
        )
        if uncovered:
            typer.echo(f"\n  \033[33m⚠\033[0m  {len(uncovered)} backend routes not covered by CLI probes:")
            for p in uncovered[:20]:
                typer.echo(f"       {p}")

    typer.echo(f"\n  {passed} passed, {failed} failed")
    if failed:
        raise typer.Exit(1)


# -- engine lifecycle management -----------------------------------------------
engine_app = typer.Typer(help="Manage the Fichero engine process.", no_args_is_help=True)
app.add_typer(engine_app, name="engine")


@engine_app.command("status")
def engine_status() -> None:
    """Show engine status (running or stopped with uptime)."""
    from fichero.cli.engine_manager import status

    status()


@engine_app.command("start")
def engine_start(
    port: int = typer.Option(8765, "--port", help="Port to run the engine on."),
    workers: int = typer.Option(
        4, "--workers", help="Number of uvicorn worker processes."
    ),
) -> None:
    """Start the engine in the background.

    Launches a detached uvicorn process and polls the port until responsive.
    If the engine is already running, prints its PID and exits.
    """
    from fichero.cli.engine_manager import start

    start(port=port, workers=workers)


@engine_app.command("stop")
def engine_stop() -> None:
    """Stop the engine gracefully.

    Attempts graceful shutdown via HTTP first, then SIGTERM, finally SIGKILL
    if the process does not respond.
    """
    from fichero.cli.engine_manager import stop

    stop()


@engine_app.command("restart")
def engine_restart(
    port: int = typer.Option(8765, "--port", help="Port to run the engine on."),
    workers: int = typer.Option(
        4, "--workers", help="Number of uvicorn worker processes."
    ),
) -> None:
    """Stop and start the engine.

    Useful for reloading configuration or recovering from a hung state.
    """
    from fichero.cli.engine_manager import restart

    restart(port=port, workers=workers)


def main() -> None:
    """Console entry point."""
    app()


if __name__ == "__main__":
    main()
