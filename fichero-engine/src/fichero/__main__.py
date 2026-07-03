"""Fichero CLI — a thin command-line client for the backend.

Every command is one or two HTTP calls through FicheroClient; there is no
backend logic here. Run ``fichero --help`` for the command tree. The console
entry point ``fichero = "fichero.__main__:main"`` is declared in pyproject.toml.
"""

from __future__ import annotations

import base64
import getpass
import json
import mimetypes
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable, Optional

import typer

from fichero.cli import FicheroClient, FicheroError
from fichero.cli import client as client_module
from fichero.cli.openapi_surface_generated import register_generated_openapi_commands
from fichero.cli.formatters import render
app = typer.Typer(
    help="Fichero CLI — a thin HTTP client for the Fichero backend.",
    no_args_is_help=True,
)
docs_app = typer.Typer(help="List and inspect documents.", no_args_is_help=True)
workflow_app = typer.Typer(help="List and run workflows.", no_args_is_help=True)
threads_app = typer.Typer(help="Manage workflow execution threads.", no_args_is_help=True)
kg_app = typer.Typer(help="Query the knowledge graph.", no_args_is_help=True)
notes_app = typer.Typer(help="Create and inspect Zettelkasten notes.", no_args_is_help=True)
library_app = typer.Typer(
    help="Create and enumerate .fichero library packages.",
    no_args_is_help=True,
)
artifacts_app = typer.Typer(
    help="List and inspect artifacts.", no_args_is_help=True
)
claim_app = typer.Typer(help="Inspect and curate knowledge claims.", no_args_is_help=True)
entity_app = typer.Typer(help="Inspect and curate knowledge entities.", no_args_is_help=True)
interpretation_app = typer.Typer(help="Inspect and curate hermeneutic interpretations.", no_args_is_help=True)
audit_app = typer.Typer(help="Review entity merge/split audit trail.", no_args_is_help=True)
settings_app = typer.Typer(help="Read and write AI-defaults settings.", no_args_is_help=True)
providers_app = typer.Typer(help="Manage LLM provider configurations.", no_args_is_help=True)
devices_app = typer.Typer(help="Manage paired devices.", no_args_is_help=True)
compare_app = typer.Typer(help="Compare models and workflows.", no_args_is_help=True)
auth_app = typer.Typer(help="Authenticate as a multi-user account.", no_args_is_help=True)
app.add_typer(docs_app, name="docs")
app.add_typer(workflow_app, name="workflow")
app.add_typer(kg_app, name="kg")
app.add_typer(notes_app, name="notes")
app.add_typer(library_app, name="library")
app.add_typer(artifacts_app, name="artifacts")
app.add_typer(claim_app, name="claim")
app.add_typer(entity_app, name="entity")
app.add_typer(interpretation_app, name="interpretation")
app.add_typer(audit_app, name="audit")
app.add_typer(settings_app, name="settings")
app.add_typer(providers_app, name="providers")
app.add_typer(devices_app, name="devices")
app.add_typer(compare_app, name="compare")
app.add_typer(auth_app, name="auth")
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
        _report_fichero_error(ctx, exc)
    typer.echo(render(data, as_json=ctx.obj["json"]))


def _read_cli_session() -> dict[str, Any]:
    try:
        payload = json.loads(client_module._CLI_SESSION_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _report_fichero_error(ctx: typer.Context, exc: FicheroError) -> None:
    if exc.status_code == 401:
        typer.secho("Authentication required. Run `fichero auth login`.", fg=typer.colors.RED, err=True)
    elif exc.status_code == 403:
        session = _read_cli_session()
        user = session.get("username")
        if not isinstance(user, str) or not user.strip():
            user_payload = session.get("user")
            if isinstance(user_payload, dict):
                maybe_username = user_payload.get("username")
                if isinstance(maybe_username, str) and maybe_username.strip():
                    user = maybe_username.strip()
        library = ctx.obj.get("library") or os.environ.get("FICHERO_LIBRARY_PATH") or "(no library selected)"
        typer.secho(
            f"Access denied for {user or 'the current user'} on {library}.",
            fg=typer.colors.RED,
            err=True,
        )
    typer.secho(str(exc), fg=typer.colors.RED, err=True)
    raise typer.Exit(code=1) from exc


def _auth_error(ctx: typer.Context, exc: FicheroError) -> None:
    if exc.status_code == 404 and "multi-user auth is disabled" in str(exc):
        typer.secho(
            "Multi-user auth is disabled on this engine.",
            fg=typer.colors.YELLOW,
            err=True,
        )
    else:
        _report_fichero_error(ctx, exc)
    raise typer.Exit(code=1) from exc


def _write_cli_session(token: str, user: Any = None) -> None:
    client_module._CLI_SESSION_PATH.parent.mkdir(parents=True, exist_ok=True)
    client_module._CLI_SESSION_PATH.write_text(
        json.dumps({"session_token": token, "user": user}, indent=2) + "\n",
        encoding="utf-8",
    )
    os.chmod(client_module._CLI_SESSION_PATH, 0o600)


def _delete_cli_session() -> None:
    try:
        client_module._CLI_SESSION_PATH.unlink()
    except FileNotFoundError:
        pass


def _resolve_required_doc_id(
    *, doc_flag: Optional[str], doc_positional: Optional[str]
) -> str:
    """Resolve doc ID from flag/positional forms and enforce non-empty value."""
    doc_id = doc_flag if doc_flag is not None else doc_positional
    if doc_id is None or not str(doc_id).strip():
        typer.secho(
            "Error: a document ID is required (positional or --doc/-d).",
            err=True,
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=2)
    return str(doc_id).strip()


def _normalize_json_payload(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return value


def _load_prompt(
    *,
    prompt: Optional[str],
    prompt_file: Optional[Path],
    default: Optional[str] = None,
) -> str:
    if prompt is not None and prompt_file is not None:
        typer.secho(
            "Error: pass either --prompt or --prompt-file, not both.",
            err=True,
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=2)
    if prompt_file is not None:
        return prompt_file.read_text(encoding="utf-8")
    if prompt is not None:
        return prompt
    if default is not None:
        return default
    typer.secho(
        "Error: either --prompt or --prompt-file is required.",
        err=True,
        fg=typer.colors.RED,
    )
    raise typer.Exit(code=2)


def _parse_models_csv(models: str) -> list[dict[str, str]]:
    parsed: list[dict[str, str]] = []
    for raw in [item.strip() for item in models.split(",") if item.strip()]:
        provider, sep, model = raw.partition("/")
        if not sep or not model.strip():
            typer.secho(
                f"Error: model '{raw}' must be in provider/model form.",
                err=True,
                fg=typer.colors.RED,
            )
            raise typer.Exit(code=2)
        parsed.append({"provider": provider.strip(), "model": model.strip()})
    if not parsed:
        typer.secho("Error: at least one model is required.", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=2)
    return parsed


def _image_to_data_uri(path: Path) -> str:
    mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _response_summary(result: dict[str, Any]) -> str:
    text = str(result.get("response") or "").replace("\n", " ").strip()
    if not text and result.get("error"):
        text = f"ERROR: {result['error']}"
    if len(text) > 80:
        return text[:77] + "..."
    return text


def _render_comparison(result: Any, *, as_json: bool) -> None:
    payload = _normalize_json_payload(result)
    if as_json:
        typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))
        return

    results = payload.get("results", []) if isinstance(payload, dict) else []
    fastest = payload.get("fastest_model") if isinstance(payload, dict) else None
    cheapest = payload.get("cheapest_model") if isinstance(payload, dict) else None

    rows: list[tuple[str, str, str, str]] = []
    for result_row in results:
        model_name = f"{result_row.get('provider', '')}/{result_row.get('model', '')}"
        badges = []
        if model_name == fastest:
            badges.append("fastest")
        if model_name == cheapest:
            badges.append("cheapest")
        if badges:
            model_name = f"{model_name} [{' '.join(badges)}]"
        rows.append(
            (
                model_name,
                f"{float(result_row.get('latency_ms') or 0):.1f}",
                f"${float(result_row.get('cost_usd') or 0):.4f}",
                _response_summary(result_row),
            )
        )

    headers = ("model", "latency_ms", "$cost", "response")
    widths = [len(h) for h in headers]
    for row in rows:
        widths = [max(widths[i], len(row[i])) for i in range(len(headers))]

    header_line = " | ".join(headers[i].ljust(widths[i]) for i in range(len(headers)))
    divider = "-+-".join("-" * widths[i] for i in range(len(headers)))
    typer.echo(header_line)
    typer.echo(divider)
    for row in rows:
        typer.echo(" | ".join(row[i].ljust(widths[i]) for i in range(len(headers))))

    if isinstance(payload, dict):
        typer.echo("")
        typer.echo(f"comparison_id: {payload.get('comparison_id', '')}")
        typer.echo(f"total_cost_usd: {float(payload.get('total_cost_usd') or 0):.4f}")
        typer.echo(f"total_latency_ms: {float(payload.get('total_latency_ms') or 0):.1f}")
        if fastest:
            typer.echo(f"fastest_model: {fastest}")
        if cheapest:
            typer.echo(f"cheapest_model: {cheapest}")


register_generated_openapi_commands(
    app,
    _invoke,
    existing_apps={
        "auth": auth_app,
        "artifacts": artifacts_app,
        "kg": kg_app,
        "library": library_app,
        "notes": notes_app,
        "providers": providers_app,
        "settings": settings_app,
    },
)


@auth_app.command("login")
def auth_login_command(
    ctx: typer.Context,
    username: Optional[str] = typer.Argument(None),
    device_label: Optional[str] = typer.Option(None, "--device-label"),
) -> None:
    login_username = (username or typer.prompt("Username")).strip()
    password = getpass.getpass("Password: ")
    try:
        with _client(ctx) as client:
            payload = client.request(
                "POST",
                "/api/auth/login",
                json={
                    "username": login_username,
                    "password": password,
                    "device_label": device_label,
                },
            )
    except FicheroError as exc:
        _auth_error(ctx, exc)
    token = payload.get("session_token") if isinstance(payload, dict) else None
    if not isinstance(token, str) or not token.strip():
        typer.secho("POST /api/auth/login returned no session_token", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    _write_cli_session(token.strip(), payload.get("user") if isinstance(payload, dict) else None)
    typer.echo(render(payload.get("user", payload), as_json=ctx.obj["json"]))


@auth_app.command("logout")
def auth_logout_command(ctx: typer.Context) -> None:
    try:
        with _client(ctx) as client:
            payload = client.request("POST", "/api/auth/logout")
    except FicheroError as exc:
        _auth_error(ctx, exc)
    _delete_cli_session()
    typer.echo(render(payload, as_json=ctx.obj["json"]))


@auth_app.command("whoami")
def auth_whoami_command(ctx: typer.Context) -> None:
    try:
        with _client(ctx) as client:
            payload = client.request("GET", "/api/auth/me")
    except FicheroError as exc:
        _auth_error(ctx, exc)
    typer.echo(render(payload, as_json=ctx.obj["json"]))


@compare_app.command("models")
def compare_models_command(
    ctx: typer.Context,
    models: str = typer.Option(..., "--models", help="Comma-separated provider/model list."),
    prompt: Optional[str] = typer.Option(None, "--prompt", help="Prompt text to compare."),
    prompt_file: Optional[Path] = typer.Option(
        None, "--prompt-file", exists=True, dir_okay=False, readable=True
    ),
    json_output: bool = typer.Option(False, "--json", help="Emit raw JSON."),
) -> None:
    comparison_prompt = _load_prompt(prompt=prompt, prompt_file=prompt_file)
    model_specs = _parse_models_csv(models)
    try:
        with _client(ctx) as client:
            result = client.compare_models(prompt=comparison_prompt, models=model_specs)
    except FicheroError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    _render_comparison(result, as_json=json_output or ctx.obj["json"])


@compare_app.command("vision")
def compare_vision_command(
    ctx: typer.Context,
    image: Path = typer.Option(..., "--image", exists=True, dir_okay=False, readable=True),
    models: str = typer.Option(..., "--models", help="Comma-separated provider/model list."),
    prompt: Optional[str] = typer.Option(None, "--prompt", help="Vision prompt."),
    prompt_file: Optional[Path] = typer.Option(
        None, "--prompt-file", exists=True, dir_okay=False, readable=True
    ),
    detail: str = typer.Option("high", "--detail", help="Vision detail level."),
    json_output: bool = typer.Option(False, "--json", help="Emit raw JSON."),
) -> None:
    comparison_prompt = _load_prompt(
        prompt=prompt,
        prompt_file=prompt_file,
        default="Describe this image in detail",
    )
    model_specs = _parse_models_csv(models)
    try:
        with _client(ctx) as client:
            result = client.compare_vision(
                images=[_image_to_data_uri(image)],
                prompt=comparison_prompt,
                models=model_specs,
                detail=detail,
            )
    except FicheroError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    _render_comparison(result, as_json=json_output or ctx.obj["json"])


@compare_app.command("tool")
def compare_tool_command(
    ctx: typer.Context,
    tool: str = typer.Option(..., "--tool", help="Workflow tool name."),
    inputs_json: Path = typer.Option(
        ..., "--inputs-json", exists=True, dir_okay=False, readable=True
    ),
    models: str = typer.Option(..., "--models", help="Comma-separated provider/model list."),
    json_output: bool = typer.Option(False, "--json", help="Emit raw JSON."),
) -> None:
    model_specs = _parse_models_csv(models)
    inputs = json.loads(inputs_json.read_text(encoding="utf-8"))
    try:
        with _client(ctx) as client:
            result = client.compare_tool(
                tool_name=tool,
                inputs=inputs,
                models=model_specs,
            )
    except FicheroError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    _render_comparison(result, as_json=json_output or ctx.obj["json"])


@compare_app.command("workflow")
def compare_workflow_command(
    ctx: typer.Context,
    workflow: str = typer.Option(..., "--workflow", help="Workflow ID."),
    doc_id: str = typer.Option(..., "--doc", help="Document ID to run."),
    models: str = typer.Option(..., "--models", help="Comma-separated provider/model list."),
    json_output: bool = typer.Option(False, "--json", help="Emit raw JSON."),
) -> None:
    model_specs = _parse_models_csv(models)
    try:
        with _client(ctx) as client:
            result = client.compare_workflow(
                workflow_id=workflow,
                doc_id=doc_id,
                models=model_specs,
            )
    except FicheroError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    _render_comparison(result, as_json=json_output or ctx.obj["json"])


# -- top-level commands ----------------------------------------------------
@app.command()
def health(ctx: typer.Context) -> None:
    """Check that the backend is up."""
    _invoke(ctx, lambda c: c.health())


@devices_app.command("list")
def devices_list(ctx: typer.Context) -> None:
    """List paired devices."""
    _invoke(ctx, lambda c: c.list_devices())


@devices_app.command("revoke")
def devices_revoke(
    ctx: typer.Context,
    device_id: str = typer.Argument(..., help="Paired device id."),
) -> None:
    """Revoke a paired device token."""
    _invoke(ctx, lambda c: c.revoke_device(device_id))


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


@app.command(name="import-slipbox")
def import_slipbox_command(
    ctx: typer.Context,
    library_path: Path = typer.Option(
        Path("~/Library/Application Support/Fichero/Slipbox.fichero"),
        "--library-path",
        help=(
            "New .fichero package to create/use. Defaults outside "
            "~/Documents so existing libraries are not touched."
        ),
    ),
    filesystem_root: Path = typer.Option(
        Path("~/code/slipbox"),
        "--filesystem-root",
        help="Filesystem slipbox notes root.",
    ),
    tinderbox_path: Path = typer.Option(
        Path("~/code/slipbox-tinderbox/slip-box.tbx"),
        "--tinderbox",
        help="Tinderbox .tbx XML file.",
    ),
    limit: Optional[int] = typer.Option(
        None,
        "--limit",
        help="Maximum Tinderbox notes and filesystem files to import from each source.",
    ),
    reset: bool = typer.Option(
        False,
        "--reset",
        help="Delete the target .fichero package before importing.",
    ),
    no_embed: bool = typer.Option(
        False,
        "--no-embed",
        help="Skip embedding creation. Imported content will not be immediately searchable.",
    ),
) -> None:
    """Import Daniel's slipbox into a fresh/searchable Fichero catalogue."""
    from fichero.importers.slipbox_import import import_slipbox_via_http

    try:
        with FicheroClient(
            base_url=ctx.obj["base_url"],
            library_path=str(library_path),
            token=ctx.obj["token"],
        ) as client:
            summary = import_slipbox_via_http(
                client,
                library_path=library_path,
                filesystem_root=filesystem_root,
                tinderbox_path=tinderbox_path,
                limit=limit,
                reset=reset,
                auto_embed=not no_embed,
            )
    except Exception as exc:
        typer.secho(f"Slipbox import failed: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    if summary.errors:
        typer.secho(
            f"Imported with {len(summary.errors)} errors.",
            fg=typer.colors.YELLOW,
            err=True,
        )
        for err in summary.errors[:10]:
            typer.echo(f"  {err}", err=True)
        if len(summary.errors) > 10:
            typer.echo(f"  ... {len(summary.errors) - 10} more", err=True)

    typer.echo(f"library: {summary.library_path}")
    typer.echo(f"root_document_id: {summary.root_document_id}")
    typer.echo(f"tinderbox_notes: {summary.tinderbox_notes}")
    typer.echo(f"filesystem_files: {summary.filesystem_files}")
    typer.echo(f"skipped_files: {summary.skipped_files}")


@app.command(name="import-sergio-corpus")
def import_sergio_corpus_command(
    ctx: typer.Context,
    library_path: Path = typer.Option(
        Path("~/Library/Application Support/Fichero/Sergio-Mosquera.fichero"),
        "--library-path",
        help="Target .fichero package to create/update.",
    ),
    source_root: Optional[Path] = typer.Option(
        None,
        "--source-root",
        help="Sergio corpus root (or set FICHERO_SERGIO_SOURCE_ROOT).",
    ),
    spreadsheet_path: Optional[Path] = typer.Option(
        None,
        "--spreadsheet-path",
        help="Catalogue spreadsheet (or set FICHERO_SERGIO_SPREADSHEET).",
    ),
    limit: Optional[int] = typer.Option(
        None,
        "--limit",
        help="Maximum source files to import.",
    ),
    reset: bool = typer.Option(False, "--reset", help="Delete target package before import."),
    no_embed: bool = typer.Option(False, "--no-embed", help="Skip embedding creation."),
) -> None:
    """Import Sergio Mosquera corpus + catalogue spreadsheet into a Fichero library."""
    from fichero.importers.sergio_import import import_sergio_corpus_via_http

    try:
        with FicheroClient(
            base_url=ctx.obj["base_url"],
            library_path=str(library_path),
            token=ctx.obj["token"],
        ) as client:
            summary = import_sergio_corpus_via_http(
                client,
                library_path=library_path,
                source_root=source_root,
                spreadsheet_path=spreadsheet_path,
                limit=limit,
                reset=reset,
                auto_embed=not no_embed,
            )
    except Exception as exc:
        typer.secho(f"Sergio corpus import failed: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    if summary.errors:
        typer.secho(
            f"Imported with {len(summary.errors)} errors.",
            fg=typer.colors.YELLOW,
            err=True,
        )
        for err in summary.errors[:10]:
            typer.echo(f"  {err}", err=True)
        if len(summary.errors) > 10:
            typer.echo(f"  ... {len(summary.errors) - 10} more", err=True)

    typer.echo(f"library: {summary.library_path}")
    typer.echo(f"root_document_id: {summary.root_document_id}")
    typer.echo(f"imported_files: {summary.imported_files}")
    typer.echo(f"spreadsheet_rows: {summary.spreadsheet_rows}")
    typer.echo(f"matched_rows: {summary.matched_rows}")
    typer.echo(f"unmatched_rows: {summary.unmatched_rows}")
    typer.echo(f"duplicate_filename_rows: {summary.duplicate_filename_rows}")
    typer.echo(f"skipped_files: {summary.skipped_files}")


@app.command(name="import-newton-marshall-diary")
def import_newton_marshall_diary_command(
    ctx: typer.Context,
    library_path: Path = typer.Option(
        Path("~/Library/Application Support/Fichero/Newton-C-Marshall.fichero"),
        "--library-path",
        help="Target .fichero package to create/update.",
    ),
    source_path: Optional[Path] = typer.Option(
        None,
        "--source-path",
        help="Newton C. Marshall diary source folder (or set FICHERO_NEWTON_SOURCE).",
    ),
    reset: bool = typer.Option(False, "--reset", help="Delete target package before import."),
    no_embed: bool = typer.Option(False, "--no-embed", help="Skip embedding creation."),
) -> None:
    """Import Newton C. Marshall diary archive into a Fichero corpus."""
    from fichero.importers.source_archive_import import import_newton_marshall_diary_via_http

    try:
        with FicheroClient(
            base_url=ctx.obj["base_url"],
            library_path=str(library_path),
            token=ctx.obj["token"],
        ) as client:
            summary = import_newton_marshall_diary_via_http(
                client,
                library_path=library_path,
                source_path=source_path,
                reset=reset,
                auto_embed=not no_embed,
            )
    except Exception as exc:
        typer.secho(f"Newton Marshall import failed: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    if summary.warnings:
        typer.secho(
            f"Imported with {len(summary.warnings)} warning(s).",
            fg=typer.colors.YELLOW,
            err=True,
        )
        for warning in summary.warnings[:10]:
            typer.echo(f"  {warning}", err=True)

    typer.echo(f"library: {summary.library_path}")
    typer.echo(f"provider: {summary.provider}")
    typer.echo(f"root_documents: {summary.root_documents}")
    typer.echo(f"files_imported: {summary.files_imported}")
    typer.echo(f"skipped: {summary.skipped}")


@app.command(name="import-istmina-mineria")
def import_istmina_mineria_command(
    ctx: typer.Context,
    library_path: Path = typer.Option(
        Path("~/Library/Application Support/Fichero/Istmina-Mineria.fichero"),
        "--library-path",
        help="Target .fichero package to create/update.",
    ),
    transcript_root: Optional[Path] = typer.Option(
        None,
        "--transcript-root",
        help="Transcribed corpus root (or set FICHERO_ISTMINA_TRANSCRIPT).",
    ),
    spreadsheet_root: Optional[Path] = typer.Option(
        None,
        "--spreadsheet-root",
        help="Spreadsheet-complete root (or set FICHERO_ISTMINA_SPREADSHEET).",
    ),
    review_root: Optional[Path] = typer.Option(
        None,
        "--review-root",
        help="Awaiting-human-check root (or set FICHERO_ISTMINA_REVIEW).",
    ),
    reset: bool = typer.Option(False, "--reset", help="Delete target package before import."),
    no_embed: bool = typer.Option(False, "--no-embed", help="Skip embedding creation."),
) -> None:
    """Import Istmina minería workflow outputs into a Fichero corpus."""
    from fichero.importers.source_archive_import import import_istmina_mineria_via_http

    try:
        with FicheroClient(
            base_url=ctx.obj["base_url"],
            library_path=str(library_path),
            token=ctx.obj["token"],
        ) as client:
            summary = import_istmina_mineria_via_http(
                client,
                library_path=library_path,
                transcript_root=transcript_root,
                spreadsheet_root=spreadsheet_root,
                review_root=review_root,
                reset=reset,
                auto_embed=not no_embed,
            )
    except Exception as exc:
        typer.secho(f"Istmina mineria import failed: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    if summary.warnings:
        typer.secho(
            f"Imported with {len(summary.warnings)} warning(s).",
            fg=typer.colors.YELLOW,
            err=True,
        )
        for warning in summary.warnings[:10]:
            typer.echo(f"  {warning}", err=True)

    typer.echo(f"library: {summary.library_path}")
    typer.echo(f"provider: {summary.provider}")
    typer.echo(f"root_documents: {summary.root_documents}")
    typer.echo(f"files_imported: {summary.files_imported}")
    typer.echo(f"skipped: {summary.skipped}")


@app.command(name="import-manifest")
def import_manifest_command(
    ctx: typer.Context,
    manifest: Path = typer.Option(
        ...,
        "--manifest",
        help="Path to a fichero-corpus-import-v1 manifest.jsonl.",
    ),
    library: Path = typer.Option(
        ...,
        "--library",
        help="Target .fichero package to create/populate.",
    ),
    api: str = typer.Option(
        None,
        "--api",
        help="Engine API base URL (default http://127.0.0.1:8765/api).",
    ),
    token_file: Path = typer.Option(
        None,
        "--token-file",
        help="Path to the engine API key (default the app's .api-key).",
    ),
    no_create_library: bool = typer.Option(
        False,
        "--no-create-library",
        help="Do not POST /api/library first; assume the library exists.",
    ),
    ingest: str = typer.Option(
        None,
        "--ingest",
        help=(
            "How each page's image is brought into the library: "
            "'link' (default — reference in place, but a local preview is "
            "always cached so the app never loads over the network), "
            "'copy' (copy bytes into the library), or "
            "'move' (copy bytes in, then delete the source ONLY if it is on a "
            "local disk — sources on network/removable volumes are never "
            "deleted). page_content always stays the manifest transcript "
            "(provenance import — no Apple Vision OCR)."
        ),
    ),
    copy_images: bool = typer.Option(
        False,
        "--copy-images/--no-copy-images",
        help="Legacy alias for '--ingest copy'. Prefer --ingest.",
    ),
) -> None:
    """Import a canonical corpus manifest into a library via the engine API.

    Reads a general ``fichero-corpus-import-v1`` manifest (any corpus) and
    creates folders, documents, image renditions (linked by default, or copied/
    moved into the library with ``--ingest``), entities, and claims through the
    engine's HTTP API. A local preview is always cached. Idempotent — safe to
    re-run.
    """
    from fichero.manifest_import import (
        DEFAULT_API_BASE,
        DEFAULT_TOKEN_FILE,
        import_manifest_via_http,
        resolve_http_token,
    )

    try:
        token = resolve_http_token(token_file or DEFAULT_TOKEN_FILE) if token_file else ctx.obj["token"]
        with FicheroClient(
            base_url=api or ctx.obj["base_url"] or DEFAULT_API_BASE.removesuffix("/api"),
            library_path=str(library),
            token=token,
        ) as client:
            summary = import_manifest_via_http(
                manifest_path=manifest,
                library_path=library,
                api_base=api or DEFAULT_API_BASE,
                token_file=token_file or DEFAULT_TOKEN_FILE,
                create_library=not no_create_library,
                copy_images=copy_images,
                ingest_mode=ingest,
                client=client,
            )
    except Exception as exc:
        typer.secho(f"Manifest import failed: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    if summary.warnings:
        typer.secho(
            f"Imported with {len(summary.warnings)} warning(s).",
            fg=typer.colors.YELLOW,
            err=True,
        )
        for warning in summary.warnings[:10]:
            typer.echo(f"  {warning}", err=True)

    typer.echo(f"library: {summary.library_path}")
    typer.echo(f"nodes_seen: {summary.nodes_seen}")
    typer.echo(f"pages_seen: {summary.pages_seen}")
    typer.echo(f"documents_created: {summary.documents_created}")
    typer.echo(f"documents_skipped: {summary.documents_skipped}")
    typer.echo(f"entities_created: {summary.entities_created}")
    typer.echo(f"entities_reused: {summary.entities_reused}")
    typer.echo(f"artifacts_created: {summary.artifacts_created}")
    typer.echo(f"artifacts_skipped: {summary.artifacts_skipped}")
    typer.echo(f"claims_created: {summary.claims_created}")
    typer.echo(f"claims_skipped: {summary.claims_skipped}")


@app.command(name="import-iiif")
def import_iiif_command(
    ctx: typer.Context,
    iiif: Path = typer.Option(
        ...,
        "--iiif",
        help="Path to a IIIF Presentation 3.0 file or directory.",
    ),
    library: Path = typer.Option(
        ...,
        "--library",
        help="Target .fichero package to create/populate.",
    ),
    api: str = typer.Option(
        None,
        "--api",
        help="Engine API base URL (default http://127.0.0.1:8765/api).",
    ),
    token_file: Path = typer.Option(
        None,
        "--token-file",
        help="Path to the engine API key (default the app's .api-key).",
    ),
    no_create_library: bool = typer.Option(
        False,
        "--no-create-library",
        help="Do not POST /api/library first; assume the library exists.",
    ),
    ingest: str = typer.Option(
        None,
        "--ingest",
        help="Image ingest mode: 'link' (default), 'copy', or 'move'.",
    ),
    copy_images: bool = typer.Option(
        False,
        "--copy-images/--no-copy-images",
        help="Legacy alias for '--ingest copy'. Prefer --ingest.",
    ),
) -> None:
    """Import IIIF Presentation 3.0 + W3C AnnotationPages via the engine API."""
    from fichero.iiif_import import (
        DEFAULT_API_BASE,
        DEFAULT_TOKEN_FILE,
        import_iiif_via_http,
        resolve_http_token,
    )

    try:
        token = resolve_http_token(token_file or DEFAULT_TOKEN_FILE) if token_file else ctx.obj["token"]
        with FicheroClient(
            base_url=api or ctx.obj["base_url"] or DEFAULT_API_BASE.removesuffix("/api"),
            library_path=str(library),
            token=token,
        ) as client:
            summary = import_iiif_via_http(
                iiif_path=iiif,
                library_path=library,
                api_base=api or DEFAULT_API_BASE,
                token_file=token_file or DEFAULT_TOKEN_FILE,
                create_library=not no_create_library,
                copy_images=copy_images,
                ingest_mode=ingest,
                client=client,
            )
    except Exception as exc:
        typer.secho(f"IIIF import failed: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    if summary.warnings:
        typer.secho(
            f"Imported with {len(summary.warnings)} warning(s).",
            fg=typer.colors.YELLOW,
            err=True,
        )
        for warning in summary.warnings[:10]:
            typer.echo(f"  {warning}", err=True)

    typer.echo(f"library: {summary.library_path}")
    typer.echo(f"manifests_seen: {summary.manifests_seen}")
    typer.echo(f"pages_seen: {summary.pages_seen}")
    typer.echo(f"documents_created: {summary.documents_created}")
    typer.echo(f"documents_skipped: {summary.documents_skipped}")
    typer.echo(f"entities_created: {summary.entities_created}")
    typer.echo(f"entities_reused: {summary.entities_reused}")
    typer.echo(f"annotations_created: {summary.annotations_created}")
    typer.echo(f"annotations_skipped: {summary.annotations_skipped}")


@app.command(name="import-archivo-judicial-medellin")
def import_archivo_judicial_medellin_command(
    ctx: typer.Context,
    library_path: Path = typer.Option(
        Path("~/Library/Application Support/Fichero/Archivo-Judicial-Medellin.fichero"),
        "--library-path",
        help="Target .fichero package to create/update.",
    ),
    catalogue_root: Optional[Path] = typer.Option(
        None,
        "--catalogue-root",
        help="Archivo Judicial de Medellin catalogue root (or set FICHERO_ARCHIVO_JUDICIAL_CATALOGUE).",
    ),
    reset: bool = typer.Option(False, "--reset", help="Delete target package before import."),
    no_embed: bool = typer.Option(False, "--no-embed", help="Skip embedding creation."),
) -> None:
    """Import Archivo Judicial de Medellin catalogue materials."""
    from fichero.importers.source_archive_import import import_archivo_judicial_medellin_via_http

    try:
        with FicheroClient(
            base_url=ctx.obj["base_url"],
            library_path=str(library_path),
            token=ctx.obj["token"],
        ) as client:
            summary = import_archivo_judicial_medellin_via_http(
                client,
                library_path=library_path,
                catalogue_root=catalogue_root,
                reset=reset,
                auto_embed=not no_embed,
            )
    except Exception as exc:
        typer.secho(f"Archivo Judicial import failed: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    if summary.warnings:
        typer.secho(
            f"Imported with {len(summary.warnings)} warning(s).",
            fg=typer.colors.YELLOW,
            err=True,
        )
        for warning in summary.warnings[:10]:
            typer.echo(f"  {warning}", err=True)

    typer.echo(f"library: {summary.library_path}")
    typer.echo(f"provider: {summary.provider}")
    typer.echo(f"root_documents: {summary.root_documents}")
    typer.echo(f"files_imported: {summary.files_imported}")
    typer.echo(f"skipped: {summary.skipped}")


@app.command(name="import-ghc-catalogued-materials")
def import_ghc_catalogued_materials_command(
    ctx: typer.Context,
    library_path: Path = typer.Option(
        Path("~/Library/Application Support/Fichero/GHC-Catalogued-Materials.fichero"),
        "--library-path",
        help="Target .fichero package to create/update.",
    ),
    acenet_root: Optional[Path] = typer.Option(
        None,
        "--acenet-root",
        help="Root for ACENET import materials (or set FICHERO_GHC_ACENET_ROOT).",
    ),
    catalogued_root: Optional[Path] = typer.Option(
        None,
        "--catalogued-root",
        help="Root for already-catalogued GHC materials (or set FICHERO_GHC_CATALOGUED_ROOT).",
    ),
    reset: bool = typer.Option(False, "--reset", help="Delete target package before import."),
    no_embed: bool = typer.Option(False, "--no-embed", help="Skip embedding creation."),
) -> None:
    """Import already-catalogued GHC materials, including ACENET imports."""
    from fichero.importers.source_archive_import import import_ghc_catalogued_materials_via_http

    try:
        with FicheroClient(
            base_url=ctx.obj["base_url"],
            library_path=str(library_path),
            token=ctx.obj["token"],
        ) as client:
            summary = import_ghc_catalogued_materials_via_http(
                client,
                library_path=library_path,
                acenet_root=acenet_root,
                catalogued_root=catalogued_root,
                reset=reset,
                auto_embed=not no_embed,
            )
    except Exception as exc:
        typer.secho(f"GHC catalogued import failed: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    if summary.warnings:
        typer.secho(
            f"Imported with {len(summary.warnings)} warning(s).",
            fg=typer.colors.YELLOW,
            err=True,
        )
        for warning in summary.warnings[:10]:
            typer.echo(f"  {warning}", err=True)

    typer.echo(f"library: {summary.library_path}")
    typer.echo(f"provider: {summary.provider}")
    typer.echo(f"root_documents: {summary.root_documents}")
    typer.echo(f"files_imported: {summary.files_imported}")
    typer.echo(f"skipped: {summary.skipped}")


@app.command(name="import-chota-colombian-pacific-maps")
def import_chota_colombian_pacific_maps_command(
    library_path: Path = typer.Option(
        Path("~/Library/Application Support/Fichero/Chota-Pacific-Maps.fichero"),
        "--library-path",
        help="Target .fichero package to create/update.",
    ),
    source_root: Optional[Path] = typer.Option(
        None,
        "--source-root",
        help=(
            "Root folder containing Chota Valley + Colombian Pacific maps corpus "
            "(or set FICHERO_CHOTA_PACIFIC_SOURCE)."
        ),
    ),
    reset: bool = typer.Option(False, "--reset", help="Delete target package before import."),
    no_embed: bool = typer.Option(False, "--no-embed", help="Skip embedding creation."),
) -> None:
    """Import Chota Valley + Colombian Pacific maps corpus."""
    from fichero.source_archive_import import import_chota_colombian_pacific_maps

    try:
        summary = import_chota_colombian_pacific_maps(
            library_path=library_path,
            source_root=source_root,
            reset=reset,
            auto_embed=not no_embed,
        )
    except Exception as exc:
        typer.secho(f"Chota/Pacific maps import failed: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    if summary.warnings:
        typer.secho(
            f"Imported with {len(summary.warnings)} warning(s).",
            fg=typer.colors.YELLOW,
            err=True,
        )
        for warning in summary.warnings[:10]:
            typer.echo(f"  {warning}", err=True)

    typer.echo(f"library: {summary.library_path}")
    typer.echo(f"provider: {summary.provider}")
    typer.echo(f"root_documents: {summary.root_documents}")
    typer.echo(f"files_imported: {summary.files_imported}")
    typer.echo(f"skipped: {summary.skipped}")


@app.command(name="import-dropbox-links")
def import_dropbox_links_command(
    library_path: Path = typer.Option(
        Path("~/Library/Application Support/Fichero/Dropbox-Links.fichero"),
        "--library-path",
        help="Target .fichero package to create/update.",
    ),
    manifest_path: Path = typer.Option(
        Path("~/Downloads/dropbox_links.json"),
        "--manifest-path",
        help="JSON or CSV manifest of Dropbox links exported from Dropbox Files API.",
    ),
    reset: bool = typer.Option(
        False,
        "--reset",
        help="Delete the target package before importing.",
    ),
) -> None:
    """Import Dropbox shared links as library references (no file download)."""

    from fichero.cloud_link_import import import_dropbox_links

    try:
        summary = import_dropbox_links(
            library_path=library_path,
            manifest_path=manifest_path,
            reset=reset,
        )
    except Exception as exc:
        typer.secho(f"Dropbox link import failed: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    if summary.errors:
        typer.secho(
            f"Imported with {len(summary.errors)} errors.",
            fg=typer.colors.YELLOW,
            err=True,
        )
        for err in summary.errors[:10]:
            typer.echo(f"  {err}", err=True)

    typer.echo(f"library: {summary.library_path}")
    typer.echo(f"root_document_id: {summary.root_document_id}")
    typer.echo(f"imported_links: {summary.imported_links}")
    typer.echo(f"skipped_rows: {summary.skipped_rows}")


@app.command(name="import-box-links")
def import_box_links_command(
    library_path: Path = typer.Option(
        Path("~/Library/Application Support/Fichero/Box-Links.fichero"),
        "--library-path",
        help="Target .fichero package to create/update.",
    ),
    manifest_path: Path = typer.Option(
        Path("~/Downloads/box_links.json"),
        "--manifest-path",
        help="JSON or CSV manifest of Box links exported from Box APIs.",
    ),
    reset: bool = typer.Option(
        False,
        "--reset",
        help="Delete the target package before importing.",
    ),
) -> None:
    """Import Box links as library references (no file download)."""

    from fichero.cloud_link_import import import_box_links

    try:
        summary = import_box_links(
            library_path=library_path,
            manifest_path=manifest_path,
            reset=reset,
        )
    except Exception as exc:
        typer.secho(f"Box link import failed: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    if summary.errors:
        typer.secho(
            f"Imported with {len(summary.errors)} errors.",
            fg=typer.colors.YELLOW,
            err=True,
        )
        for err in summary.errors[:10]:
            typer.echo(f"  {err}", err=True)

    typer.echo(f"library: {summary.library_path}")
    typer.echo(f"root_document_id: {summary.root_document_id}")
    typer.echo(f"imported_links: {summary.imported_links}")
    typer.echo(f"skipped_rows: {summary.skipped_rows}")


@app.command(name="import-tinderbox-links")
def import_tinderbox_links_command(
    library_path: Path = typer.Option(
        Path("~/Library/Application Support/Fichero/Tinderbox-Links.fichero"),
        "--library-path",
        help="Target .fichero package to create/update.",
    ),
    tbx_path: Path = typer.Option(
        Path("~/Documents/Notes.tbx"),
        "--tbx-path",
        help="Path to the Tinderbox .tbx document.",
    ),
    reset: bool = typer.Option(
        False,
        "--reset",
        help="Delete the target package before importing.",
    ),
) -> None:
    """Import/link Tinderbox notes from a .tbx file into the library model."""

    from fichero.tinderbox_link_import import import_tinderbox_links

    try:
        summary = import_tinderbox_links(
            library_path=library_path,
            tbx_path=tbx_path,
            reset=reset,
        )
    except Exception as exc:
        typer.secho(f"Tinderbox link import failed: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    if summary.errors:
        typer.secho(
            f"Imported with {len(summary.errors)} errors.",
            fg=typer.colors.YELLOW,
            err=True,
        )
        for err in summary.errors[:10]:
            typer.echo(f"  {err}", err=True)

    typer.echo(f"library: {summary.library_path}")
    typer.echo(f"tbx_path: {summary.tbx_path}")
    typer.echo(f"root_document_id: {summary.root_document_id}")
    typer.echo(f"imported_notes: {summary.imported_notes}")
    typer.echo(f"updated_notes: {summary.updated_notes}")
    typer.echo(f"deleted_notes: {summary.deleted_notes}")
    typer.echo(f"skipped_notes: {summary.skipped_notes}")


@artifacts_app.command("list")
def artifacts_list(
    ctx: typer.Context,
    doc_id_positional: Optional[str] = typer.Argument(
        None, help="Document ID (positional form)."
    ),
    doc: Optional[str] = typer.Option(
        None, "--doc", "-d", help="Document ID (flag form; overrides positional)."
    ),
    artifact_type: Optional[str] = typer.Option(
        None, "--type", help="Filter by artifact type."
    ),
    limit: int = typer.Option(50, "--limit"),
) -> None:
    """List a document's artifacts.

    Accepts the document ID as either a positional argument or via ``--doc/-d``.
    Both forms are equivalent; ``--doc`` overrides the positional when both are
    supplied.
    """
    doc_id = _resolve_required_doc_id(doc_flag=doc, doc_positional=doc_id_positional)
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
_SEARCH_SCOPE_CHOICES = ("content", "entities", "claims")


def _validate_search_type(value: str) -> str:
    """Typer callback — accept the four choices, normalize aliases."""
    normalized = (value or "").lower()
    if normalized not in _SEARCH_TYPE_CHOICES:
        raise typer.BadParameter(
            f"'{value}' is not one of {list(_SEARCH_TYPE_CHOICES)}."
        )
    return _SEARCH_TYPE_ALIASES.get(normalized, normalized)


def _normalize_search_scopes(values: list[str]) -> list[str] | None:
    """Accept repeated and comma-separated --scope flags."""
    if not values:
        return None
    normalized_scopes: list[str] = []
    for raw_value in values:
        for part in raw_value.split(","):
            scope = part.strip().lower()
            if not scope:
                continue
            if scope not in _SEARCH_SCOPE_CHOICES:
                raise typer.BadParameter(
                    f"'{scope}' is not one of {list(_SEARCH_SCOPE_CHOICES)}."
                )
            if scope not in normalized_scopes:
                normalized_scopes.append(scope)
    return normalized_scopes or None


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
    scope: list[str] = typer.Option(
        [],
        "--scope",
        help="Search scopes: content, entities, claims. Repeat or pass a comma-separated list.",
    ),
) -> None:
    """Search documents. Use --in-doc / --in-folder to scope results."""
    include = _normalize_search_scopes(scope)
    if ctx.obj["json"]:
        _invoke(
            ctx,
            lambda c: c.search(
                query,
                limit=limit,
                search_type=search_type,
                include=include,
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
                include=include,
                doc_id=in_doc,
                folder_id=in_folder,
            )
    except FicheroError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    from fichero.cli.formatters import render_claim

    payload = data.model_dump(mode="json") if hasattr(data, "model_dump") else data

    # Try to render as search results with custom formatting first
    results = payload.get("results") if isinstance(payload, dict) else payload
    entity_hits = payload.get("entity_hits") if isinstance(payload, dict) else None
    claim_hits = payload.get("claim_hits") if isinstance(payload, dict) else None
    if isinstance(results, list) and results:
        typer.echo(f"results ({len(results)}):")
        for r in results:
            # If result has claim-like structure, use render_claim
            if isinstance(r, dict) and "subject_canonical" in r:
                typer.echo(f"  {render_claim(r)}")
            else:
                # Fall back to custom search result formatting
                typer.echo(_render_search_result_item(r))
    elif isinstance(payload, dict):
        typer.echo(_render_search_results(payload))
    else:
        typer.echo(_render_search_results(payload))

    if isinstance(entity_hits, list) and entity_hits:
        typer.echo(f"entity hits ({len(entity_hits)}):")
        for entity in entity_hits:
            if not isinstance(entity, dict):
                typer.echo(f"  - {entity}")
                continue
            name = entity.get("canonical_name") or entity.get("name") or "(unnamed entity)"
            entity_id = str(entity.get("id") or "?")[:8]
            score = entity.get("similarity_score")
            score_str = f"{score:.3f}" if isinstance(score, (int, float)) else "  -  "
            typer.echo(f"  {score_str}  {entity_id}  {name}")

    if isinstance(claim_hits, list) and claim_hits:
        typer.echo(f"claim hits ({len(claim_hits)}):")
        for claim in claim_hits:
            if isinstance(claim, dict) and "subject_canonical" in claim:
                typer.echo(f"  {render_claim(claim)}")
            else:
                typer.echo(f"  - {claim}")


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


# -- notes -----------------------------------------------------------------
@notes_app.command("create")
def notes_create(
    ctx: typer.Context,
    body: str = typer.Argument(..., help="Markdown body for the note."),
    title: Optional[str] = typer.Option(None, "--title", help="Optional note title."),
    kind: str = typer.Option("zettel", "--kind", help="Note kind."),
    tags: Optional[list[str]] = typer.Option(None, "--tag", help="Repeatable tag."),
    linked_note_ids: Optional[list[str]] = typer.Option(
        None, "--note", help="Repeatable linked note ID."
    ),
    linked_entity_ids: Optional[list[str]] = typer.Option(
        None, "--entity", help="Repeatable linked entity ID."
    ),
    linked_claim_ids: Optional[list[str]] = typer.Option(
        None, "--claim", help="Repeatable linked claim ID."
    ),
    linked_document_ids: Optional[list[str]] = typer.Option(
        None, "--doc", help="Repeatable linked document ID."
    ),
    page_id: Optional[str] = typer.Option(None, "--page", help="Primary page scope document ID."),
    folder_id: Optional[str] = typer.Option(None, "--folder", help="Primary folder scope document ID."),
    address: Optional[str] = typer.Option(None, "--address"),
    parent_address: Optional[str] = typer.Option(None, "--parent-address"),
) -> None:
    """Create a Zettelkasten note."""
    kwargs = {
        "title": title,
        "body": body,
        "kind": kind,
        "tags": tags,
        "linked_note_ids": linked_note_ids,
        "linked_entity_ids": linked_entity_ids,
        "linked_claim_ids": linked_claim_ids,
        "linked_document_ids": linked_document_ids,
        "address": address,
        "parent_address": parent_address,
    }
    if page_id is not None:
        kwargs["page_id"] = page_id
    if folder_id is not None:
        kwargs["folder_id"] = folder_id
    _invoke(
        ctx,
        lambda c: c.create_note(**kwargs),
    )


@notes_app.command("list")
def notes_list(
    ctx: typer.Context,
    kind: Optional[str] = typer.Option(None, "--kind", help="Filter by note kind."),
    tag: Optional[str] = typer.Option(None, "--tag", help="Filter by tag."),
    linked_entity_id: Optional[str] = typer.Option(None, "--entity"),
    linked_claim_id: Optional[str] = typer.Option(None, "--claim"),
    linked_document_id: Optional[str] = typer.Option(None, "--doc"),
    page_id: Optional[str] = typer.Option(None, "--page", help="Filter by page scope document ID."),
    folder_id: Optional[str] = typer.Option(None, "--folder", help="Filter by folder scope document ID."),
    query: Optional[str] = typer.Option(None, "--query", "-q", help="Text search."),
) -> None:
    """List Zettelkasten notes."""
    kwargs = {
        "kind": kind,
        "tag": tag,
        "linked_entity_id": linked_entity_id,
        "linked_claim_id": linked_claim_id,
        "linked_document_id": linked_document_id,
        "query": query,
    }
    if page_id is not None:
        kwargs["page_id"] = page_id
    if folder_id is not None:
        kwargs["folder_id"] = folder_id
    _invoke(
        ctx,
        lambda c: c.list_notes(**kwargs),
    )


@notes_app.command("get")
def notes_get(
    ctx: typer.Context, note_id: str = typer.Argument(..., help="Note ID.")
) -> None:
    """Show a single Zettelkasten note."""
    _invoke(ctx, lambda c: c.get_note(note_id))


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
    from pydantic import BaseModel as _BaseModel
    for entry in payload:
        # The real client returns list[ActivityResponse] (model objects); only
        # a not-yet-migrated path would yield dicts. Normalise to a dict so the
        # terminal-type check and downstream _merge_terminal_payload both work.
        data = entry.model_dump() if isinstance(entry, _BaseModel) else entry
        if isinstance(data, dict) and data.get("type") in _TERMINAL_ACTIVITY_TYPES:
            return data
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
    entity_type: Optional[str] = typer.Option(
        None, "--type", help="Filter by entity type."
    ),
    limit: int = typer.Option(
        50, "--limit", help="Maximum number of entities to return."
    ),
) -> None:
    """List knowledge-graph entities across the library."""
    _invoke(ctx, lambda c: c.list_entities(entity_type=entity_type, limit=limit))


@kg_app.command("claims")
def kg_claims(
    ctx: typer.Context,
    doc_id_positional: Optional[str] = typer.Argument(
        None, help="Document ID (positional form)."
    ),
    doc: Optional[str] = typer.Option(
        None, "--doc", "-d", help="Document ID (flag form; overrides positional)."
    ),
    limit: int = typer.Option(50, "--limit"),
) -> None:
    """List knowledge-graph claims sourced from a document.

    Accepts the document ID as either a positional argument or via ``--doc/-d``.
    Both forms are equivalent; ``--doc`` overrides the positional when both are
    supplied.
    """
    doc_id = _resolve_required_doc_id(doc_flag=doc, doc_positional=doc_id_positional)
    _invoke(
        ctx,
        lambda c: c.list_claims(source_document_id=doc_id, limit=limit),
    )


@kg_app.command("citations")
def kg_citations(
    ctx: typer.Context,
    doc_id_positional: Optional[str] = typer.Argument(
        None, help="Document ID (positional form)."
    ),
    doc: Optional[str] = typer.Option(
        None, "--doc", "-d", help="Document ID (flag form; overrides positional)."
    ),
) -> None:
    """List citation entities resolved for a document.

    Accepts the document ID as either a positional argument or via ``--doc/-d``.
    Both forms are equivalent; ``--doc`` overrides the positional when both are
    supplied.
    """
    doc_id = _resolve_required_doc_id(doc_flag=doc, doc_positional=doc_id_positional)
    _invoke(ctx, lambda c: c.citations_at_doc(doc_id))


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
    Path.home() / "code",
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


@library_app.command("snapshot")
def library_snapshot(
    ctx: typer.Context,
    path: Optional[str] = typer.Argument(
        None,
        help="Path to the .fichero package. Defaults to --library/FICHERO_LIBRARY_PATH.",
    ),
    reason: str = typer.Option("", "--reason", "-r", help="Reason stored in manifest."),
) -> None:
    """Create a database and embedding snapshot for a library."""
    library_path = path or ctx.obj.get("library")
    if not library_path:
        typer.secho(
            "Error: provide a library path or pass --library.",
            err=True,
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=2)
    expanded = str(Path(library_path).expanduser())

    def op(c: FicheroClient) -> dict:
        snapshot = c.create_library_snapshot(expanded, reason=reason)
        return {
            "status": f"Snapshot: {snapshot.id}",
            "library": snapshot.library_path,
            "reason": snapshot.reason,
            "duckdb_size_bytes": snapshot.duckdb_size_bytes,
            "lance_size_bytes": snapshot.lance_size_bytes,
        }

    _invoke(ctx, op)


@library_app.command("snapshots")
def library_snapshots(
    ctx: typer.Context,
    library_name: Optional[str] = typer.Option(
        None, "--library-name", help="Filter by library package name."
    ),
    include_expired: bool = typer.Option(
        False, "--include-expired", help="Include expired snapshots."
    ),
) -> None:
    """List library snapshots."""
    _invoke(
        ctx,
        lambda c: c.list_library_snapshots(
            library_name=library_name,
            include_expired=include_expired,
        ),
    )


@library_app.command("restore")
def library_restore(
    ctx: typer.Context,
    snapshot_id: str = typer.Argument(..., help="Snapshot ID to restore."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
) -> None:
    """Restore a snapshot into its original library package."""
    if not yes:
        typer.confirm(
            f"Restore snapshot {snapshot_id} into its original library package?",
            abort=True,
        )
    _invoke(ctx, lambda c: c.restore_library_snapshot(snapshot_id))


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
    """Close a library: unregister it from the global registry (#1661).

    The .fichero package on disk is NOT deleted — only its registry entry is
    removed, so it no longer shows up in ``library list`` or the app sidebar.
    Idempotent: closing an unregistered library is a no-op success.

    Output: "Closed: {path}"
    """
    expanded = str(Path(path).expanduser())

    def op(c: FicheroClient) -> dict:
        c.remove_known_library(expanded)
        return {"status": f"Closed: {expanded}"}

    _invoke(ctx, op)


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
    page_content: Optional[str] = typer.Option(
        None, "--page-content", help="New page content (transcript/body text)."
    ),
    page_content_file: Optional[str] = typer.Option(
        None,
        "--page-content-file",
        help="Read new page content from a file (use '-' for stdin). Wins over --page-content.",
    ),
) -> None:
    """Update editable fields on a document."""
    fields: dict[str, Any] = {}
    if name is not None:
        fields["name"] = name
    if parent_id is not None:
        fields["parent_id"] = parent_id
    if folder_path is not None:
        fields["folder_path"] = folder_path
    if page_content_file is not None:
        if page_content_file == "-":
            page_content = sys.stdin.read()
        else:
            page_content = Path(page_content_file).read_text(encoding="utf-8")
    if page_content is not None:
        fields["page_content"] = page_content
    if not fields:
        typer.secho(
            "No fields to update — pass --name, --parent-id, --folder-path, "
            "--page-content, or --page-content-file.",
            err=True,
        )
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


@docs_app.command("split-chapters")
def docs_split_chapters(
    ctx: typer.Context,
    doc_id: str = typer.Argument(..., help="Book PDF document ID."),
) -> None:
    """Run the Split Chapters workflow for a book PDF."""
    _invoke(ctx, lambda c: c.split_chapters(doc_id))


@docs_app.command("translate")
def docs_translate(
    ctx: typer.Context,
    doc_id: str = typer.Argument(..., help="Document ID."),
    to: str = typer.Option("en", "--to", help="Target language code (e.g. en, nl, es)."),
    source: str = typer.Option("auto", "--source", help="Source language code or auto."),
) -> None:
    """Run the Translate workflow for one document."""
    _invoke(
        ctx,
        lambda c: c.translate_document(
            doc_id,
            target_lang=to,
            source_lang=source,
        ),
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


# -- interpretation --------------------------------------------------------
@interpretation_app.command("create")
def interpretation_create(
    ctx: typer.Context,
    framework_id: str = typer.Option(..., "--framework-id", help="Interpretive framework ID."),
    text: str = typer.Option(..., "--text", help="Interpretation text."),
    act: str = typer.Option(..., "--act", help="Interpretive act (applying, contextualizing, comparing, critiquing, synthesizing)."),
    predicate: Optional[str] = typer.Option(None, "--predicate", help="Hermeneutic predicate (raw or canonical)."),
    claim_id: Optional[str] = typer.Option(None, "--claim-id", help="Optional claim ID target."),
    doc_id: Optional[str] = typer.Option(None, "--doc-id", help="Optional document ID target."),
    passage_text: Optional[str] = typer.Option(None, "--passage-text", help="Optional raw passage target."),
    confidence: float = typer.Option(0.5, "--confidence", help="Confidence [0..1]."),
) -> None:
    """Create a hermeneutic interpretation."""
    _invoke(
        ctx,
        lambda c: c.create_interpretation(
            framework_id=framework_id,
            interpretation_text=text,
            act=act,
            predicate=predicate,
            claim_id=claim_id,
            document_id=doc_id,
            passage_text=passage_text,
            confidence=confidence,
        ),
    )


@interpretation_app.command("list")
def interpretation_list(
    ctx: typer.Context,
    framework_id: Optional[str] = typer.Option(None, "--framework-id", help="Filter by framework ID."),
    claim_id: Optional[str] = typer.Option(None, "--claim-id", help="Filter by claim ID."),
    act: Optional[str] = typer.Option(None, "--act", help="Filter by interpretive act."),
    limit: int = typer.Option(50, "--limit"),
) -> None:
    """List hermeneutic interpretations."""
    _invoke(
        ctx,
        lambda c: c.list_interpretations(
            framework_id=framework_id,
            claim_id=claim_id,
            act=act,
            limit=limit,
        ),
    )


@interpretation_app.command("get")
def interpretation_get(
    ctx: typer.Context,
    interpretation_id: str = typer.Argument(..., help="Interpretation ID."),
) -> None:
    """Show one hermeneutic interpretation."""
    _invoke(ctx, lambda c: c.get_interpretation(interpretation_id))


@interpretation_app.command("update")
def interpretation_update(
    ctx: typer.Context,
    interpretation_id: str = typer.Argument(..., help="Interpretation ID."),
    text: Optional[str] = typer.Option(None, "--text", help="New interpretation text."),
    act: Optional[str] = typer.Option(None, "--act", help="New interpretive act."),
    predicate: Optional[str] = typer.Option(None, "--predicate", help="Hermeneutic predicate (raw or canonical)."),
    confidence: Optional[float] = typer.Option(None, "--confidence", help="Confidence [0..1]."),
) -> None:
    """Update an existing hermeneutic interpretation."""
    fields: dict[str, Any] = {}
    if text is not None:
        fields["interpretation_text"] = text
    if act is not None:
        fields["act"] = act
    if predicate is not None:
        fields["predicate"] = predicate
    if confidence is not None:
        fields["confidence"] = confidence
    if not fields:
        typer.secho("Pass at least one updatable field.", err=True)
        raise typer.Exit(code=1)
    _invoke(ctx, lambda c: c.update_interpretation(interpretation_id, **fields))


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

    from fichero.cli.formatters import render_top_entity

    if isinstance(entities, list):
        for entity in entities:
            typer.echo(render_top_entity(entity))
    else:
        typer.echo(render_top_entity(entities))


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


@entity_app.command("inspector")
def entity_inspector_cmd(
    ctx: typer.Context,
    entity_id: str = typer.Argument(..., help="Entity ID."),
) -> None:
    """Full inspector view: claims grouped by source document in dense prose format.

    Shows each source document as a section header, with all claims from that
    source as a dense semicolon-separated line. Time, place, and asserter
    annotations appear inline where available.
    """
    if ctx.obj["json"]:
        _invoke(ctx, lambda c: c.entity_inspector(entity_id))
        return
    try:
        with _client(ctx) as client:
            data = client.entity_inspector(entity_id)
    except FicheroError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    entity = data.entity
    name = entity.canonical_name if entity else entity_id
    etype = (entity.entity_type or "").value if entity and entity.entity_type else ""
    desc = (entity.description or "") if entity else ""
    claim_count = data.claim_count or len(data.claims or [])

    typer.secho(f"{name}  [{etype}]  {claim_count} claims", bold=True)
    if desc:
        typer.echo(desc)

    # Group claims by source_document_id + source_page_label
    from collections import defaultdict
    groups: dict[tuple[str, str], list] = defaultdict(list)
    for claim in data.claims or []:
        doc_id = claim.source_document_id or ""
        page = claim.source_page_label or ""
        groups[(doc_id, page)].append(claim)

    # Build doc name lookup from data.documents
    doc_names: dict[str, str] = {}
    for doc in data.documents or []:
        if doc.id:
            doc_names[doc.id] = doc.name or doc.id[:8]

    for (doc_id, page), claims in groups.items():
        doc_name = doc_names.get(doc_id, doc_id[:8] if doc_id else "unknown")
        section = doc_name
        if page:
            section += f" — p. {page}"
        bar = "─" * max(0, 60 - len(section))
        typer.secho(f"\n── {section} {bar}", fg=typer.colors.BRIGHT_BLACK)

        # Build dense semicolon-separated line with inline annotations
        parts = []
        for claim in claims:
            text = (claim.text or "").strip()
            if not text:
                continue
            annotations = []
            if claim.temporal_context:
                annotations.append(f"⏱ {claim.temporal_context}")
            if claim.claim_location:
                annotations.append(f"📍 {claim.claim_location}")
            if claim.speaker_name:
                annotations.append(f"👤 {claim.speaker_name}")
            if annotations:
                text = text.rstrip(".") + f" ({'; '.join(annotations)})"
            parts.append(text)
        typer.echo("; ".join(parts) if parts else "(no claim text)")


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
        "/api/kg/query/examples", "/api/kg/query/sparql",
        "/api/kg/export/rdf",
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
    host: str | None = typer.Option(
        None,
        "--host",
        help=(
            "Bind host for the engine. Defaults to FICHERO_BIND_HOST or "
            "127.0.0.1. Non-loopback binds are refused by default; use "
            "tailscale serve or SSH loopback forwarding for remote access."
        ),
    ),
    workers: int = typer.Option(
        1,
        "--workers",
        help="uvicorn worker processes. Must be 1 — the engine is "
        "single-process (DuckDB single-writer + in-process change-stream hub); "
        "values >1 are clamped to 1 (#2044).",
    ),
) -> None:
    """Start the engine in the background.

    Launches a detached uvicorn process and polls the port until responsive.
    If the engine is already running, prints its PID and exits.
    """
    from fichero.cli.engine_manager import start

    start(port=port, workers=workers, host=host)


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
    host: str | None = typer.Option(
        None,
        "--host",
        help=(
            "Bind host for the engine. Defaults to FICHERO_BIND_HOST or "
            "127.0.0.1. Non-loopback binds are refused by default; use "
            "tailscale serve or SSH loopback forwarding for remote access."
        ),
    ),
    workers: int = typer.Option(
        1,
        "--workers",
        help="uvicorn worker processes. Must be 1 — the engine is "
        "single-process (DuckDB single-writer + in-process change-stream hub); "
        "values >1 are clamped to 1 (#2044).",
    ),
) -> None:
    """Stop and start the engine.

    Useful for reloading configuration or recovering from a hung state.
    """
    from fichero.cli.engine_manager import restart

    restart(port=port, workers=workers, host=host)


def main() -> None:
    """Console entry point."""
    app()


if __name__ == "__main__":
    main()
