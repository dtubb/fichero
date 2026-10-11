"""#5664 (ruled 2026-10-11: Start fetches its own downloads): Start sets up the local model runtime a step needs.

Seen 2026-10-11 on a first-run onboarding from a source engine: every step on Qwen2.5-VL failed, "The download of
Qwen2.5-VL 7B (OCR) could not be done: MLX runtime is not provisioned (needs both mlx-lm and mlx-vlm): no interpreter
at …/mlx-runtime/bin/python. Call POST /api/local-inference/runtime/provision or enable Local Models in Settings…".

- When a step runs on this Mac's local model server and its runtime is not set up, the plan's downloads include
  setting it up, named in words, and Ready's sentence says so; Start queues it as a job in Activity (the one
  download path), and the steps wait for it.
- A model download that finds the runtime missing sets it up first rather than failing.
- No sentence a person reads names an API route or a file path.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fichero_server.execution import jobs
from fichero_server.llm import mlx_runtime
from fichero_server.llm.local_models import DOWNLOAD_KIND
from tests.unit.recipes.test_installed_model_first_to_spec import CORRECT, LINES, READ, mac  # noqa: F401
from tests.unit.recipes.test_recipe_execution_to_spec import _recipe, _save, engine, pages  # noqa: F401


class _FakeRuntime(mlx_runtime.MLXRuntime):
    """The real runtime's bookkeeping, with venv creation and pip stubbed: setting up writes the metadata only."""

    def __init__(self, root: Path) -> None:
        self.commands: list[list[str]] = []

        def create_venv(target: Path) -> None:
            (target / "bin").mkdir(parents=True, exist_ok=True)
            (target / "bin" / "python").write_text("")

        super().__init__(root / "mlx-runtime", create_venv=create_venv, run_command=self.commands.append)

    def is_provisioned(self) -> bool:
        return self.python_path().exists() and bool(self._metadata().get("mlx_vlm_version"))


@pytest.fixture
def runtime(monkeypatch, tmp_path):
    fake = _FakeRuntime(tmp_path)
    monkeypatch.setattr(mlx_runtime, "get_mlx_runtime", lambda: fake)
    monkeypatch.setattr("fichero_server.llm.mlx_model_store.get_mlx_runtime", lambda: fake)
    monkeypatch.setattr(mlx_runtime, "bundled_versions", lambda: None)
    return fake


def _words(plan: dict) -> str:
    return json.dumps({k: plan.get(k) for k in ("refusals", "waiting", "start_downloads", "skipped")})


def test_the_plan_sets_up_the_runtime_a_local_step_needs(jobs_run_by_the_test, client, db, pages, mac, runtime):
    _save(client, _recipe(None, LINES, READ, CORRECT), cloud_allowed=False)
    plan = client.get("/api/recipes/project/start").json()

    (setup,) = [d for d in plan["downloads"] if d["runtime"] == "mlx-runtime"]
    assert setup["steps"] == ["correct"] and setup["params"] == {"runtime": "mlx-runtime", "model": "mlx"}
    assert setup["name"] == "the local model runtime", setup
    assert "the local model runtime" in plan["start_downloads"]["sentence"], plan["start_downloads"]
    assert plan["refusals"] == []
    assert "/api/" not in _words(plan) and "mlx-runtime/bin" not in _words(plan)

    started = client.post("/api/recipes/project/start")
    assert started.status_code == 200, started.text
    queued = [r for r in jobs.jobs_on_subjects(db, ["mlx-runtime:mlx"]) if r["kind"] == DOWNLOAD_KIND]
    assert len(queued) == 1, "setting up the runtime is a job in Activity"
    detail = json.loads(jobs.read_job(db, started.json()["started"]["job_id"])["detail"])
    assert {"steps": ["correct"], "job_id": queued[0]["id"], "name": "the local model runtime"} in detail["awaited"]


def test_the_plan_names_no_runtime_once_it_is_set_up(client, db, pages, mac, runtime):
    runtime.provision_now()
    _save(client, _recipe(None, LINES, READ, CORRECT), cloud_allowed=False)
    plan = client.get("/api/recipes/project/start").json()
    assert not [d for d in plan["downloads"] if d["runtime"] == "mlx-runtime"]


def test_the_setup_job_sets_the_runtime_up(runtime, db):
    from fichero_server.llm.local_models import _run_download

    assert not runtime.is_provisioned()
    _run_download("mlx-runtime:mlx", db)
    assert runtime.is_provisioned()
    assert any("mlx-vlm" in " ".join(c) for c in runtime.commands)


def test_a_model_download_sets_the_runtime_up_first(runtime):
    assert runtime.ensure_provisioned() == runtime.python_path()
    assert runtime.is_provisioned()


def test_no_runtime_message_names_a_route_or_a_path(runtime, monkeypatch):
    monkeypatch.setattr(runtime, "_run_command", lambda argv: (_ for _ in ()).throw(RuntimeError("pip failed")))
    for said in (_raised(runtime.require_python_path), _raised(runtime.require_audio_python_path),
                 _raised(runtime.ensure_provisioned)):
        assert "/api/" not in said and "POST" not in said and str(runtime.runtime_dir) not in said, said
        assert "bin/python" not in said, said


def _raised(fn) -> str:
    try:
        fn()
    except Exception as exc:  # noqa: BLE001 -- the sentence is what is tested
        return str(exc)
    raise AssertionError(f"{fn.__name__} did not refuse")
