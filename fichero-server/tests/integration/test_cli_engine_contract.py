"""Live CLI<->engine contract test — the CLI mirror of the Swift
AppEngineContractTests.

Spawns a real uvicorn on an ephemeral port (so it never contends with the app's
:8765 or the Swift harness), seeds a disposable library via the shared seeder,
and drives the real cli.FicheroClient against it. Asserts the values the CLI
decodes equal the library's ground truth — proving the CLI's hand-written
request/parse layer faithfully matches the engine, the gap mock tests can't cover.
"""

from __future__ import annotations

import os
import socket
import subprocess
import time
from pathlib import Path

import httpx
import pytest

from fichero_cli import FicheroClient

REPO_ROOT = Path(__file__).resolve().parents[3]
VENV_UVICORN = REPO_ROOT / ".venv" / "bin" / "uvicorn"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_healthy(base_url: str, timeout: float = 30.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            r = httpx.get(f"{base_url}/api/health", timeout=2.0)
            if r.status_code == 200 and r.json().get("status") == "healthy":
                return True
        except httpx.HTTPError:
            pass
        time.sleep(0.3)
    return False


@pytest.fixture(scope="module")
def cli_against_seed(tmp_path_factory):
    """Spawn an engine on a free port, seed a library, yield (client, summary)."""
    if not VENV_UVICORN.exists():
        pytest.skip(f"venv uvicorn not found at {VENV_UVICORN}")

    from tests.integration._seedlib import seed

    workdir = tmp_path_factory.mktemp("cli-itest")
    library = workdir / "library.fichero"
    summary = seed(library)

    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    env = {
        **os.environ,
        "PYTHONPATH": str(REPO_ROOT / "fichero-server" / "src"),
        "FICHERO_DISABLE_AUTH": "1",
        "FICHERO_FEATURE_TIER": "dev",
        "FICHERO_SKIP_DEFAULT_WORKFLOWS": "1",
        "FICHERO_BASE_PATH": str(workdir / "base"),
        "FICHERO_PARENT_PID": str(os.getpid()),
    }
    # Capture the engine's stderr so a failed boot is diagnosable (not silent).
    engine_log = workdir / "engine.log"
    log_handle = open(engine_log, "w")
    proc = subprocess.Popen(
        [str(VENV_UVICORN), "fichero_server.api.main:app", "--host", "127.0.0.1", "--port", str(port)],
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
        client = FicheroClient(base_url=base_url, library_path=str(library), token=None)
        try:
            yield client, summary
        finally:
            client.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        log_handle.close()


def _expected(summary, key):
    return summary["expected"][key]


def test_cli_documents_match_library(cli_against_seed):
    client, summary = cli_against_seed
    assert len(client.list_documents()) == _expected(summary, "documents_total")
    children = client.list_documents(parent_id=summary["keys"]["collection"])
    assert len(children) == _expected(summary, "children_of_collection")


def test_cli_workflows_match_library(cli_against_seed):
    client, summary = cli_against_seed
    assert len(client.list_workflows()) == _expected(summary, "workflows")


def test_cli_entities_match_library(cli_against_seed):
    client, summary = cli_against_seed
    assert len(client.list_entities()) == _expected(summary, "entities")


def test_cli_claims_match_library(cli_against_seed):
    client, summary = cli_against_seed
    assert len(client.list_claims()) == _expected(summary, "claims")


def test_cli_artifacts_match_library(cli_against_seed):
    client, summary = cli_against_seed
    arts = client.list_artifacts(summary["keys"]["doc_letter"], include_descendants=False)
    assert len(arts) == _expected(summary, "artifacts_for_letter")


def test_cli_create_read_delete_round_trip(cli_against_seed):
    client, _ = cli_against_seed
    created = client.create_entity("ITest Entity", entity_type="other")
    fetched = client.get_entity(created.id)
    assert fetched.id == created.id
    assert fetched.canonical_name == "ITest Entity"
    client.delete_entity(created.id)
