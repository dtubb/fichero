"""Live smoke test for generated OpenAPI GET commands."""

from __future__ import annotations

import importlib.util
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

os.environ.setdefault("FICHERO_FEATURE_TIER", "dev")
os.environ.setdefault("FICHERO_SKIP_DEFAULT_WORKFLOWS", "1")
os.environ.setdefault("FICHERO_DISABLE_AUTH", "1")

from fichero import __main__ as cli  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[3]
VENV_UVICORN = Path(sys.executable).parent / "uvicorn"
_GENERATOR_PATH = REPO_ROOT / "fichero-engine" / "scripts" / "generate_openapi_cli.py"
_GENERATOR_SPEC = importlib.util.spec_from_file_location("generate_openapi_cli", _GENERATOR_PATH)
if _GENERATOR_SPEC is None or _GENERATOR_SPEC.loader is None:  # pragma: no cover - import wiring
    raise ImportError(f"could not load generator at {_GENERATOR_PATH}")
_generator = importlib.util.module_from_spec(_GENERATOR_SPEC)
sys.modules[_GENERATOR_SPEC.name] = _generator
_GENERATOR_SPEC.loader.exec_module(_generator)

runner = CliRunner()

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
    "/api/chains/presets/paleography",
    "/api/citations/export",
    "/api/citations/document/{document_id}",
    "/api/citations/document/{document_id}.bib",
    "/api/documents/{doc_id}/notes",
    "/api/entities/{entity_id}/drill-down",
    "/api/iiif/iiif/image/{document_id}",
    "/api/iiif/iiif/manifest/{document_id}",
    "/api/images/{document_id}/preview",
    "/api/kg/claim-search",
    "/api/kg/claim-search/{claim_id}/similar",
    "/api/kg/entity-curation/semantic",
    "/api/storage/display/{doc_id}",
    "/api/storage/source/{doc_id}",
    "/api/storage/thumbnail/{doc_id}",
    "/api/tasks/tasks",
    "/api/workflow-execution/workflows/{workflow_id}/visualization",
    "/api/workflow-execution/workflows/{workflow_id}/visualization.png",
    "/view/document/{doc_id}",
    "/view/kg/global",
}
_MAX_SKIPPED_GET_COMMANDS = 115
_MIN_EXECUTABLE_GET_COMMANDS = 160


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


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_healthy(base_url: str, timeout: float = 30.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            response = httpx.get(f"{base_url}/api/health", timeout=2.0)
            if response.status_code == 200 and response.json().get("status") == "healthy":
                return True
        except httpx.HTTPError:
            pass
        time.sleep(0.3)
    return False


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


def _path_values(summary: dict) -> dict[str, str]:
    return {
        "artifact_id": summary["keys"]["artifact"],
        "claim_id": summary["ids"]["claims"][0],
        "doc_id": summary["keys"]["doc_letter"],
        "document_id": summary["keys"]["doc_letter"],
        "entity_id": summary["keys"]["entity_person"],
        "folder_id": summary["keys"]["collection"],
        "page_doc_id": summary["keys"]["page"],
        "workflow_id": summary["keys"]["workflow"],
    }


def _args_for(operation, command_name: str, summary: dict, base_url: str, library_path: Path) -> list[str] | None:
    if any(operation.path.startswith(prefix) for prefix in _SKIP_PREFIXES):
        return None
    if operation.path in _SKIP_PATHS:
        return None

    path_values = _path_values(summary)
    args = [
        "--base-url",
        base_url,
        "--library",
        str(library_path),
        _generator.RESOURCE_NAME_OVERRIDES.get(operation.resource, operation.resource),
        command_name,
    ]

    for path_param in operation.path_params:
        value = path_values.get(path_param)
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


@pytest.fixture(scope="module")
def cli_smoke_env(tmp_path_factory):
    if not VENV_UVICORN.exists():
        pytest.skip(f"venv uvicorn not found at {VENV_UVICORN}")

    from tests.integration._seedlib import seed

    workdir = tmp_path_factory.mktemp("cli-generated-smoke")
    library = workdir / "library.fichero"
    summary = seed(library)

    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    env = {
        **os.environ,
        "PYTHONPATH": str(REPO_ROOT / "fichero-engine" / "src"),
        "FICHERO_DISABLE_AUTH": "1",
        "FICHERO_FEATURE_TIER": "dev",
        "FICHERO_SKIP_DEFAULT_WORKFLOWS": "1",
        "FICHERO_BASE_PATH": str(workdir / "base"),
        "FICHERO_PARENT_PID": str(os.getpid()),
    }
    engine_log = workdir / "engine.log"
    log_handle = open(engine_log, "w")
    process = subprocess.Popen(
        [str(VENV_UVICORN), "fichero.api.main:app", "--host", "127.0.0.1", "--port", str(port)],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=log_handle,
    )
    try:
        if not _wait_healthy(base_url):
            tail = engine_log.read_text(errors="replace")[-4000:]
            pytest.fail(
                "spawned engine never became healthy in 30s.\n"
                f"--- engine stderr (tail) ---\n{tail}"
            )
        yield {
            "base_url": base_url,
            "engine_log": engine_log,
            "library": library,
            "summary": summary,
        }
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
        log_handle.close()


def test_generated_get_commands_succeed_against_seeded_library(cli_smoke_env):
    executable: list[tuple[str, list[str]]] = []
    skipped: list[str] = []
    for operation, command_name in _generated_get_operations():
        args = _args_for(
            operation,
            command_name,
            cli_smoke_env["summary"],
            cli_smoke_env["base_url"],
            cli_smoke_env["library"],
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
        tail = cli_smoke_env["engine_log"].read_text(errors="replace")[-4000:]
        lines = [f"  {path} -> exit {code}: {output}" for path, code, output in failures[:25]]
        pytest.fail(
            "Generated CLI GET smoke failures:\n"
            + "\n".join(lines)
            + f"\n--- engine stderr (tail) ---\n{tail}"
        )
