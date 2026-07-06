"""Shared live-engine fixture for CLI contract tests."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

os.environ.setdefault("FICHERO_FEATURE_TIER", "dev")
os.environ.setdefault("FICHERO_SKIP_DEFAULT_WORKFLOWS", "1")
os.environ.setdefault("FICHERO_DISABLE_AUTH", "1")

REPO_ROOT = Path(__file__).resolve().parents[3]
VENV_UVICORN = Path(sys.executable).parent / "uvicorn"
_PARAM_FALLBACK = "contract-walk-nonexistent"


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


def path_values(summary: dict) -> dict[str, str]:
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


def fill_path(template: str, summary: dict) -> str:
    out = template
    while "{" in out:
        start = out.index("{")
        end = out.index("}", start)
        name = out[start + 1 : end]
        value = path_values(summary).get(name, _PARAM_FALLBACK)
        out = out[:start] + value + out[end + 1 :]
    return out


@pytest.fixture(scope="module")
def cli_live_engine(tmp_path_factory):
    if not VENV_UVICORN.exists():
        pytest.skip(f"venv uvicorn not found at {VENV_UVICORN}")

    from tests.integration._seedlib import seed

    workdir = tmp_path_factory.mktemp("cli-live")
    library = workdir / "library.fichero"
    summary = seed(library)

    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    env = {
        **os.environ,
        # Keep startup library discovery/recovery inside the temp harness.
        # Otherwise live CLI contracts can walk real ~/Documents libraries and
        # stall on external volumes before /api/health ever responds.
        "HOME": str(workdir),
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
