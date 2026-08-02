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


def _reclaim_contents(path: Path) -> None:
    """tests/conftest.py's reclaim_tmp_path_contents, found by file path.

    Same trap and same lookup technique as perf/conftest.py: the workdir is a
    ``tmp_path_factory`` NUMBERED dir, so removing it outright frees its
    number for reuse (the e767147e5 stale path-keyed-cache incident) —
    contents are emptied and the dir itself stays.
    """
    root_path = (Path(__file__).resolve().parents[1] / "conftest.py").resolve()
    for module in list(sys.modules.values()):
        if getattr(module, "__file__", None) and Path(module.__file__).resolve() == root_path:
            module.reclaim_tmp_path_contents(path)
            return
    raise RuntimeError("tests/conftest.py not loaded — cannot reclaim live-engine workdir")


def _share_real_model_cache(workdir: Path) -> None:
    """Point the spawned engine's fake HOME at the REAL model cache (#4434).

    The fixture redirects HOME into the workdir (necessary — startup library
    discovery must stay inside the harness), but the engine's models dir
    hangs off HOME, so every integration run RE-DOWNLOADED the 2.2 GB
    e5-large ONNX embedding model into temp and then leaked it. A symlink to
    the real cache means no download and nothing to leak; if the real cache
    is absent (fresh CI), the engine downloads into the workdir as before and
    teardown reclaims it. The models tree is a shared CACHE, not library
    data — the harness's isolation rule protects Daniel's library, and this
    shares only what a real engine on this machine would populate anyway.
    """
    real_models = Path.home() / "Library" / "Application Support" / "Fichero" / "models"
    if not real_models.is_dir():
        return
    fake_fichero = workdir / "Library" / "Application Support" / "Fichero"
    fake_fichero.mkdir(parents=True, exist_ok=True)
    (fake_fichero / "models").symlink_to(real_models)


@pytest.fixture(scope="module")
def cli_live_engine(tmp_path_factory):
    if not VENV_UVICORN.exists():
        pytest.skip(f"venv uvicorn not found at {VENV_UVICORN}")

    from tests.integration._seedlib import seed

    workdir = tmp_path_factory.mktemp("cli-live")
    _share_real_model_cache(workdir)
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
        "PYTHONPATH": str(REPO_ROOT / "fichero-server" / "src"),
        "FICHERO_DISABLE_AUTH": "1",
        "FICHERO_FEATURE_TIER": "dev",
        "FICHERO_SKIP_DEFAULT_WORKFLOWS": "1",
        "FICHERO_BASE_PATH": str(workdir / "base"),
        "FICHERO_PARENT_PID": str(os.getpid()),
    }
    engine_log = workdir / "engine.log"
    log_handle = open(engine_log, "w")
    process = subprocess.Popen(
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
        # #4434: the engine is dead, nothing holds handles into workdir —
        # reclaim the module's whole footprint (seeded library, engine base,
        # any model the engine downloaded into the fake HOME). The model-cache
        # symlink is removed FIRST and explicitly: shutil.rmtree refuses to
        # walk a symlinked dir (so the REAL cache can never be deleted through
        # it), but with ignore_errors=True that refusal is silent and the link
        # would linger.
        models_link = workdir / "Library" / "Application Support" / "Fichero" / "models"
        if models_link.is_symlink():
            models_link.unlink(missing_ok=True)
        _reclaim_contents(workdir)
