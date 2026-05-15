"""Fichero CLI — a thin command-line client for the backend.

Every command is one or two HTTP calls through FicheroClient; there is no
backend logic here. Run ``fichero --help`` for the command tree. The console
entry point ``fichero = "fichero.__main__:main"`` is declared in pyproject.toml.
"""

from __future__ import annotations

import time
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
app.add_typer(docs_app, name="docs")
app.add_typer(workflow_app, name="workflow")
app.add_typer(kg_app, name="kg")

# Execution statuses that mean the run has stopped — used by `workflow run --wait`.
_TERMINAL_STATUSES = frozenset(
    {"completed", "complete", "failed", "error", "cancelled", "canceled", "done"}
)
_POLL_INTERVAL_SECONDS = 1.0
_POLL_MAX_ATTEMPTS = 600  # ~10 minutes ceiling


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


@app.command(name="import")
def import_file(
    ctx: typer.Context,
    path: str = typer.Argument(..., help="File to import into the library."),
    parent: Optional[str] = typer.Option(
        None, "--parent", help="Parent folder document ID."
    ),
) -> None:
    """Import a file into the library (multipart upload)."""
    _invoke(ctx, lambda c: c.import_file(path, parent_id=parent))


@app.command()
def artifacts(
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


def _poll_until_terminal(client: FicheroClient, thread_id: str) -> Any:
    """Poll execution status until the run reaches a terminal state.

    The backend creates the LangGraph checkpoint asynchronously after
    ``execute`` returns, and fast or no-op runs may finish before any
    checkpoint is written — so a 404 from the status endpoint is "not ready
    yet", not a fatal error. Keep polling on 404; bail out only when something
    real goes wrong. If the poll budget is exhausted, raise a FicheroError
    rather than returning ``None`` silently — a `--wait` that ends with no
    information must surface as a failure.
    """
    status: Any = None
    only_saw_404 = True
    for _ in range(_POLL_MAX_ATTEMPTS):
        try:
            status = client.execution_status(thread_id)
            only_saw_404 = False
        except FicheroError as exc:
            if exc.status_code == 404:
                time.sleep(_POLL_INTERVAL_SECONDS)
                continue
            raise
        state = ""
        if isinstance(status, dict):
            state = str(status.get("status", "")).lower()
        if state in _TERMINAL_STATUSES:
            return status
        time.sleep(_POLL_INTERVAL_SECONDS)
    if only_saw_404:
        raise FicheroError(
            f"Timed out waiting for workflow thread {thread_id}: status endpoint "
            f"returned 404 for the entire poll window. The workflow may have "
            f"completed without producing a checkpoint — check `fichero activity`."
        )
    raise FicheroError(
        f"Timed out waiting for workflow thread {thread_id} to reach a terminal "
        f"state. Last seen status: {status!r}"
    )


@workflow_app.command("run")
def workflow_run(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Workflow name or ID."),
    doc_id: str = typer.Argument(..., help="Document ID to run the workflow on."),
    wait: bool = typer.Option(
        False, "--wait", help="Poll until the run completes or fails."
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
                result = _poll_until_terminal(client, thread_id)
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


def main() -> None:
    """Console entry point."""
    app()


if __name__ == "__main__":
    main()
