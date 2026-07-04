"""Live smoke test for generated OpenAPI GET commands."""

from __future__ import annotations

import importlib.util
import os
import socket
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

os.environ.setdefault("FICHERO_FEATURE_TIER", "dev")
os.environ.setdefault("FICHERO_SKIP_DEFAULT_WORKFLOWS", "1")
os.environ.setdefault("FICHERO_DISABLE_AUTH", "1")

from fichero import __main__ as cli  # noqa: E402
from tests.integration._cli_live import cli_live_engine as _cli_live_engine, path_values  # noqa: E402,F401

cli_live_engine = _cli_live_engine

REPO_ROOT = Path(__file__).resolve().parents[3]
_GENERATOR_PATH = REPO_ROOT / "fichero-engine" / "scripts" / "generate_openapi_cli.py"
_GENERATOR_SPEC = importlib.util.spec_from_file_location("generate_openapi_cli", _GENERATOR_PATH)
if _GENERATOR_SPEC is None or _GENERATOR_SPEC.loader is None:  # pragma: no cover - import wiring
    raise ImportError(f"could not load generator at {_GENERATOR_PATH}")
_generator = importlib.util.module_from_spec(_GENERATOR_SPEC)
sys.modules[_GENERATOR_SPEC.name] = _generator
_GENERATOR_SPEC.loader.exec_module(_generator)

runner = CliRunner()

_COMMAND_RESOURCE_OVERRIDES = {
    "claims": ("claim",),
    "documents": ("docs",),
    "entities": ("entity",),
    "hermeneutics": ("interpretation",),
    "workflow-execution": ("workflow", "threads"),
    "workflows": ("workflow",),
}
_REQUIRED_QUERY_VALUES = {
    "language": "en",
    "q": "Eugenio",
    "room_id": "missing-room",
    "source": "test-ent-person",
    "source_language": "en",
    "target": "test-ent-place",
}
_SKIP_PREFIXES = (
    "/api/integrations/",
    "/api/models",
    "/api/mcp-servers/",
)
_SKIP_PATHS = {
    "/api/auth/me",
    "/api/chains/presets/paleography",
    "/api/changes/stream",
    "/api/citations/document/{document_id}",
    "/api/citations/document/{document_id}.bib",
    "/api/documents/{doc_id}/notes",
    "/api/entities/{entity_id}/drill-down",
    "/api/iiif/iiif/image/{document_id}",
    "/api/iiif/iiif/manifest/{document_id}",
    "/api/kg/claim-search",
    "/api/kg/claim-search/{claim_id}/similar",
    "/api/kg/entity-curation/semantic",
    "/api/pair/devices",
    "/api/tasks/tasks",
    "/api/users",
    "/api/workflow-execution/workflows/{workflow_id}/visualization",
    "/api/workflow-execution/workflows/{workflow_id}/visualization.png",
}
_MAX_SKIPPED_GET_COMMANDS = 118
_MIN_EXECUTABLE_GET_COMMANDS = 194
_BINARY_IMAGE_PATHS = {
    "/api/images/{document_id}/preview",
    "/api/storage/display/{doc_id}",
    "/api/storage/source/{doc_id}",
    "/api/storage/thumbnail/{doc_id}",
}


def _cli_smoke_ready() -> bool:
    """Generated CLI smoke is opt-in and requires loopback socket access."""
    if os.getenv("FICHERO_RUN_CLI_GENERATED_GET_SMOKE") != "1":
        return False
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
    except OSError:
        return False
    return True


pytestmark = pytest.mark.skipif(
    not _cli_smoke_ready(),
    reason="Generated CLI smoke is opt-in and requires loopback socket access",
)


def _generated_get_operations():
    seen_per_resource: dict[str, set[str]] = {}
    operations = []
    for operation in _generator._build_operations():
        if operation.method != "GET":
            continue
        command_name = _generator._command_name(
            operation,
            seen_per_resource.setdefault(operation.resource, set()),
        )
        operations.append((operation, command_name))
    return operations


def _args_for(operation, command_name: str, summary: dict, base_url: str, library_path: Path) -> list[str] | None:
    if any(operation.path.startswith(prefix) for prefix in _SKIP_PREFIXES):
        return None
    if operation.path in _SKIP_PATHS:
        return None

    values = path_values(summary)
    if operation.path == "/api/documents/{doc_id}/workspace/items":
        values["doc_id"] = summary["keys"]["collection"]
    if operation.path in _BINARY_IMAGE_PATHS:
        values["doc_id"] = summary["keys"]["doc_photo"]
        values["document_id"] = summary["keys"]["doc_photo"]
    resource_parts = _COMMAND_RESOURCE_OVERRIDES.get(
        operation.resource,
        (_generator.RESOURCE_NAME_OVERRIDES.get(operation.resource, operation.resource),),
    )
    args = [
        "--base-url",
        base_url,
        "--library",
        str(library_path),
        *resource_parts,
        command_name,
    ]

    for path_param in operation.path_params:
        value = values.get(path_param)
        if value is None:
            return None
        args.append(value)

    for query_param in operation.query_params:
        if not query_param.required:
            continue
        value = _REQUIRED_QUERY_VALUES.get(query_param.name)
        if value is None:
            return None
        args.extend([f"--{query_param.name.replace('_', '-')}", value])

    return args


def test_generated_get_commands_succeed_against_seeded_library(cli_live_engine):
    executable: list[tuple[str, list[str]]] = []
    skipped: list[str] = []
    for operation, command_name in _generated_get_operations():
        args = _args_for(
            operation,
            command_name,
            cli_live_engine["summary"],
            cli_live_engine["base_url"],
            cli_live_engine["library"],
        )
        if args is None:
            skipped.append(operation.path)
            continue
        executable.append((operation.path, args))

    assert len(skipped) <= _MAX_SKIPPED_GET_COMMANDS
    assert len(executable) >= _MIN_EXECUTABLE_GET_COMMANDS

    failures = []
    for path, args in executable:
        print(f"CLI smoke GET {path}", flush=True)
        result = runner.invoke(cli.app, args)
        if result.exit_code != 0:
            failures.append((path, result.exit_code, result.output[-500:]))

    if failures:
        tail = cli_live_engine["engine_log"].read_text(errors="replace")[-4000:]
        lines = [f"  {path} -> exit {code}: {output}" for path, code, output in failures[:25]]
        pytest.fail(
            "Generated CLI GET smoke failures:\n"
            + "\n".join(lines)
            + f"\n--- engine stderr (tail) ---\n{tail}"
        )
