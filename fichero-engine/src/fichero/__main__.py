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
kg_app = typer.Typer(help="Query the knowledge graph.", no_args_is_help=True)
library_app = typer.Typer(
    help="Create and enumerate .fichero library packages.",
    no_args_is_help=True,
)
artifacts_app = typer.Typer(
    help="List and inspect artifacts.", no_args_is_help=True
)
app.add_typer(docs_app, name="docs")
app.add_typer(workflow_app, name="workflow")
app.add_typer(kg_app, name="kg")
app.add_typer(library_app, name="library")
app.add_typer(artifacts_app, name="artifacts")

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
    _invoke(
        ctx, lambda c: c.list_artifacts(doc_id, artifact_type=artifact_type, limit=limit)
    )


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


@app.command()
def search(
    ctx: typer.Context,
    query: str = typer.Argument(..., help="Search query."),
    limit: int = typer.Option(10, "--limit"),
    search_type: str = typer.Option("hybrid", "--type", help="Search mode."),
) -> None:
    """Search documents."""
    _invoke(ctx, lambda c: c.search(query, limit=limit, search_type=search_type))


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
    if isinstance(status, dict):
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
            thread_id = result.get("thread_id") if isinstance(result, dict) else None
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
    typer.echo(render(result, as_json=ctx.obj["json"]))


# -- knowledge graph -------------------------------------------------------
def _entities_from_inspector(payload: Any) -> Any:
    """Pull just the ``entities`` array out of the inspector response.

    The inspector endpoint returns ``{entities, claims, artifacts, ...}``;
    a command named ``entities`` should show only entities. If the payload
    isn't a dict we trust the backend and return it untouched.
    """
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


@library_app.command("create")
def library_create(
    ctx: typer.Context,
    path: str = typer.Argument(
        ...,
        help="Path to the .fichero package to create (e.g. ~/Documents/Test.fichero).",
    ),
) -> None:
    """Create a fresh .fichero library and initialize its tables."""
    expanded = str(Path(path).expanduser())
    _invoke(ctx, lambda c: c.create_library(expanded))


@library_app.command("list")
def library_list(ctx: typer.Context) -> None:
    """List .fichero packages found under the allowlist roots.

    Pure filesystem walk — does NOT call the backend, so this works even
    when the engine isn't running.
    """
    paths = _discover_libraries()
    if ctx.obj["json"]:
        typer.echo(render({"libraries": paths}, as_json=True))
    else:
        typer.echo(render(paths))


def main() -> None:
    """Console entry point."""
    app()


if __name__ == "__main__":
    main()
