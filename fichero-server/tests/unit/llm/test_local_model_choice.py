"""The local model this Mac runs is chosen, switched and refused by one set of facts (#5520, #5496).

WHY: measured 2026-10-06 on 16 GB Macs, the local vision model could be changed ONLY by an
environment variable at engine start. With Qwen2.5-VL 3B installed (the one vision model that fits
16 GB), every read failed telling the person to switch it in Settings › AI, where nothing did; the
default was Qwen3-VL 8B, whose own catalogue note says reading a page needs 24 GB+; every text
default named Apple Intelligence, which that engine build did not carry, so entity extraction
failed; and a recipe step that named its own model was served the global one. These tests pin the
four promises that replace that: the server serves the model a step asks for (switching models),
Settings' local model chooses the default, defaults come from what this Mac can run and this build
carries, and a model that cannot run here is refused in the plan with the reason and the fix.

No real model is downloaded or loaded and no real RAM is read: the store's "installed" set, this
Mac's memory and the server process are all stubbed.
"""
from __future__ import annotations

from typing import Any

import pytest

from fichero_server import llm
from fichero_server.api.routes.ai import local_inference as routes
from fichero_server.llm import LLMConfig
from fichero_server.llm import local_model_choice as choice
from fichero_server.llm.local_inference import (
    LocalInferenceCapabilities,
    LocalInferenceServiceManager,
    LocalServiceState,
)
from fichero_server.llm.mlx_model_store import MANAGED_MLX_MODELS, MLXModelStore

GB = 1024**3


class _Store(MLXModelStore):
    """The real store's catalogue and naming, with a stubbed set of installed models."""

    def __init__(self, tmp_path, installed: set[str]) -> None:
        super().__init__(root=tmp_path / "mlx")
        self.installed = set(installed)

    def is_complete(self, spec: Any) -> bool:
        return spec.model_id in self.installed

    def resolve_model_path(self, model_id: str) -> str:
        return f"/models/{self.canonical_id(model_id)}"


class _Process:
    def __init__(self, running: bool = False) -> None:
        self.pid: int | None = 4242 if running else None
        self.last_error: str | None = None
        self.running = running
        self.stops = 0

    async def start(self) -> None:
        self.running, self.pid = True, 4343

    async def stop(self) -> None:
        self.stops += 1
        self.running, self.pid = False, None

    def is_running(self) -> bool:
        return self.running


class _Healthy:
    async def get_json(self, url: str, timeout_seconds: float) -> dict[str, Any]:
        return {"status": "ok"}


@pytest.fixture
def mac(monkeypatch, tmp_path, app_db):
    """A 16 GB Apple-silicon Mac with no models installed, no dev override, and server processes
    that are fakes; `mac.ram(...)` and `mac.install(...)` change it."""
    monkeypatch.delenv(choice.DEV_MODEL_ENV, raising=False)
    monkeypatch.delenv("FICHERO_OMLX_COMMAND", raising=False)
    state = {"ram": 16 * GB}
    store = _Store(tmp_path, set())

    def capabilities() -> LocalInferenceCapabilities:
        return LocalInferenceCapabilities(system="Darwin", machine="arm64", is_apple_silicon=True,
                                          physical_memory_bytes=state["ram"], macos_version="26.0")

    monkeypatch.setattr("fichero_server.llm.local_inference.get_local_inference_capabilities", capabilities)
    monkeypatch.setattr("fichero_server.llm.mlx_model_store.get_mlx_model_store", lambda: store)
    monkeypatch.setattr(choice, "_store", lambda: store)

    def new_manager(profile):
        manager = LocalInferenceServiceManager(profile, _Process(), _Healthy(), poll_interval_seconds=0)
        routes._MANAGERS[profile.id] = manager
        return manager

    monkeypatch.setattr(routes, "_new_manager", new_manager)
    routes._MANAGERS.clear()

    class Mac:
        app = app_db

        @staticmethod
        def ram(gb: int) -> None:
            state["ram"] = gb * GB

        @staticmethod
        def install(*model_ids: str) -> None:
            store.installed.update(model_ids)

        @staticmethod
        def loaded(model_id: str) -> LocalInferenceServiceManager:
            """A server already up with `model_id` in memory."""
            manager = LocalInferenceServiceManager(
                routes._configured_omlx_profile(model_id), _Process(running=True), _Healthy())
            manager.state = LocalServiceState.healthy
            routes._MANAGERS[manager.profile.id] = manager
            return manager

    yield Mac
    routes._MANAGERS.clear()


def _served() -> str:
    return routes._MANAGERS[routes.DEFAULT_OMLX_PROFILE_ID].profile.model_id


# --- the server serves the model a step asks for -------------------------------------------------


@pytest.mark.asyncio
async def test_a_step_asking_for_the_installed_3b_while_the_8b_is_loaded_is_served_the_3b(mac):
    """The #5388 refusal is gone: the server unloads the 8B and loads the 3B the step named."""
    mac.install("Qwen2.5-VL-3B", "mlx-community/Qwen3-VL-8B")
    eight = mac.loaded("mlx-community/Qwen3-VL-8B")

    await llm._ensure_managed_local_provider_ready(LLMConfig(provider="omlx", model="Qwen2.5-VL-3B"),
                                                   capability="vision")

    assert eight.process.stops == 1, "the 8B must be unloaded, not left holding the port and memory"
    assert _served() == "Qwen2.5-VL-3B"
    assert routes._MANAGERS[routes.DEFAULT_OMLX_PROFILE_ID].status().healthy


@pytest.mark.asyncio
async def test_a_recipe_pin_by_hub_repository_is_the_same_model(mac):
    """A recipe pins the Hub repository, the CLI the catalogue id: both name one model, and the
    request is sent with the snapshot path the server loaded, never the raw name (#4560)."""
    mac.install("Qwen2.5-VL-3B")
    config = LLMConfig(provider="omlx", model="mlx-community/Qwen2.5-VL-3B-Instruct-4bit")
    await llm._ensure_managed_local_provider_ready(config, capability="vision")
    assert _served() == "Qwen2.5-VL-3B"
    assert llm.get_langchain_model(config).model_name == "/models/Qwen2.5-VL-3B"


@pytest.mark.asyncio
async def test_the_model_already_loaded_is_not_restarted(mac):
    mac.install("Qwen2.5-VL-3B")
    three = mac.loaded("Qwen2.5-VL-3B")
    await llm._ensure_managed_local_provider_ready(LLMConfig(provider="omlx", model="Qwen2.5-VL-3B"))
    assert three.process.stops == 0 and routes._MANAGERS[routes.DEFAULT_OMLX_PROFILE_ID] is three


# --- a step's own model always wins (#5496) ------------------------------------------------------


@pytest.mark.asyncio
async def test_a_steps_model_beats_settings_local_model(mac, client):
    """Settings' local model is only the default for a request that names none."""
    mac.install("Qwen2.5-VL-3B", "Qwen2.5-VL-7B")
    assert client.put("/api/settings/ai-defaults", json={"local_model": "Qwen2.5-VL-3B"}).status_code == 200
    await llm._ensure_managed_local_provider_ready(
        LLMConfig(provider="omlx", model="mlx-community/Qwen2.5-VL-7B-Instruct-4bit"), capability="vision")
    assert _served() == "Qwen2.5-VL-7B"


# --- Settings' local model chooses the default ---------------------------------------------------


@pytest.mark.asyncio
async def test_settings_local_model_changes_what_is_served(mac, client):
    """The setting the error messages name is real: it changes the profile and what a request
    naming no model is served -- no environment variable, no restart."""
    mac.install("Qwen2.5-VL-3B", "Nanonets-OCR")
    assert client.put("/api/settings/ai-defaults", json={"local_model": "Nanonets-OCR"}).status_code == 200

    assert client.get("/api/local-inference/profiles").json()["items"][0]["model_id"] == "Nanonets-OCR"
    got = client.get("/api/settings/ai-defaults").json()
    assert got["local_model"] == "Nanonets-OCR"
    assert choice.LOCAL_MODEL_SETTING_NAME in got["chosen_because"]["local_model"]

    await llm._ensure_managed_local_provider_ready(LLMConfig(provider="omlx", model="local-model"))
    assert _served() == "Nanonets-OCR"


def test_settings_refuses_a_local_model_this_mac_cannot_run(mac, client):
    """16 GB cannot read a page with the 8B (its own card: 24 GB+), so Settings will not take it."""
    response = client.put("/api/settings/ai-defaults", json={"local_model": "mlx-community/Qwen3-VL-8B"})
    assert response.status_code == 422
    assert "24 GB" in response.json()["detail"]
    assert client.put("/api/settings/ai-defaults", json={"local_model": "no-such/model"}).status_code == 422


def test_the_dev_override_still_wins_for_development(mac, monkeypatch):
    monkeypatch.setenv(choice.DEV_MODEL_ENV, "Qwen2.5-VL-3B")
    assert routes._configured_omlx_profile().model_id == "Qwen2.5-VL-3B"


# --- defaults come from what this Mac can run and has installed ----------------------------------


def test_on_16_gb_the_default_local_model_is_one_that_fits(mac):
    """Never the 8B on 16 GB: nothing installed gives the verified 3B, and says to install it."""
    pick = choice.default_local_model()
    assert pick.model_id == "Qwen2.5-VL-3B"
    assert "install it" in pick.reason and "24 GB" in pick.reason


def test_an_installed_model_that_fits_is_preferred(mac):
    mac.install("Nanonets-OCR")
    pick = choice.default_local_model()
    assert pick.model_id == "Nanonets-OCR" and "installed" in pick.reason


def test_a_mac_with_room_gets_the_strongest_reader(mac):
    mac.ram(32)
    assert choice.default_local_model().model_id == "mlx-community/Qwen3-VL-8B"


def test_the_8b_still_runs_text_on_16_gb():
    """Its card's floor for loading is 16 GB; only reading a page needs 24 GB (#4560)."""
    spec = MANAGED_MLX_MODELS["mlx-community/Qwen3-VL-8B"]
    sixteen = LocalInferenceCapabilities(system="Darwin", machine="arm64", is_apple_silicon=True,
                                         physical_memory_bytes=16 * GB)
    assert choice.runs_here(spec, "text", capabilities=sixteen) == (True, None)
    ok, why = choice.runs_here(spec, "vision", capabilities=sixteen)
    assert not ok and "24 GB" in why and "16 GB" in why


# --- never a provider this build lacks -----------------------------------------------------------


def test_without_apple_intelligence_text_defaults_fall_to_the_local_server_and_say_so(mac):
    mac.install("Qwen2.5-VL-3B")
    values, because = choice.machine_ai_defaults(apple_intelligence=False)
    for tier in ("text", "small", "medium", "large"):
        assert values[f"default_{tier}_provider"] == "omlx"
        assert values[f"default_{tier}_model"] == "Qwen2.5-VL-3B"
        assert "Apple Intelligence is not in this build" in because[f"default_{tier}_provider"]
    # Apple Vision and Apple Speech are system frameworks, not the fm-bridge: they stay.
    assert values["default_vision_model"] == "apple-vision" and values["default_audio_model"] == "apple-speech"


def test_with_apple_intelligence_the_factory_baseline_stands(mac):
    values, _ = choice.machine_ai_defaults(apple_intelligence=True)
    assert values["default_text_provider"] == "apple" and values["default_text_model"] == "apple-intelligence"


def test_reset_and_first_launch_seed_what_this_build_can_run(mac, monkeypatch):
    from fichero_server.api.main import _ensure_default_ai_defaults

    mac.install("Qwen3-4B-Instruct")
    monkeypatch.setattr(choice, "apple_intelligence_in_this_build", lambda: False)
    mac.app.reset_ai_defaults()
    assert mac.app.get_setting("default_small_provider") == "omlx"
    assert mac.app.get_setting("default_small_model") == "Qwen3-4B-Instruct"
    assert "Apple Intelligence" in choice.read_chosen_because(mac.app)["default_small_provider"]

    mac.app.delete_setting("default_large_provider")
    mac.app.delete_setting("default_large_model")
    _ensure_default_ai_defaults(mac.app, "")
    assert mac.app.get_setting("default_large_provider") == "omlx"


def test_an_old_apple_seed_moves_when_this_build_lacks_it_and_a_choice_is_kept(mac, monkeypatch):
    from fichero_server.api.main import _repair_known_bad_ai_defaults

    mac.install("Qwen2.5-VL-3B")
    monkeypatch.setattr(choice, "apple_intelligence_in_this_build", lambda: False)
    mac.app.set_setting("default_text_provider", "apple")
    mac.app.set_setting("default_text_model", "apple-intelligence")
    mac.app.set_setting("default_large_provider", "openrouter")
    mac.app.set_setting("default_large_model", "anthropic/claude-sonnet-4.6")
    _repair_known_bad_ai_defaults(mac.app)
    assert (mac.app.get_setting("default_text_provider"), mac.app.get_setting("default_text_model")) == (
        "omlx", "Qwen2.5-VL-3B")
    assert mac.app.get_setting("default_large_provider") == "openrouter"


# --- a model that cannot run here is refused before anything starts ------------------------------


def _plan(*steps):
    from fichero_server.recipes.start import plan_start

    return plan_start({"fichero_recipe": 1, "id": "t", "version": "0.1.0", "title": "t", "steps": list(steps)},
                      stays_local=True)


def _read_with(repo: str) -> dict:
    return {"id": "read", "job": "read-a-page", "model": {"hf": repo, "revision": "main"}, "runs_on": "this-mac"}


def test_the_plan_refuses_a_model_whose_card_says_this_mac_cannot_run_it(mac):
    plan = _plan(_read_with("mlx-community/Qwen3-VL-8B-Instruct-4bit"))
    [refusal] = plan["refusals"]
    assert "steps read cannot run on this Mac" in refusal
    assert "24 GB" in refusal and "Choose Qwen2.5-VL 3B (OCR) instead" in refusal


def test_the_plan_refuses_a_model_not_installed_and_says_how_to_install_it(mac):
    mac.install("Qwen2.5-VL-3B")
    [refusal] = _plan(_read_with("mlx-community/Qwen2.5-VL-7B-Instruct-4bit"))["refusals"]
    assert "Qwen2.5-VL 7B (OCR) is not installed" in refusal and "Settings › AI › Local models" in refusal
    assert "Qwen2.5-VL 3B (OCR)" in refusal


def test_the_plan_runs_an_installed_model_that_fits_as_the_steps_own(mac):
    mac.install("Qwen2.5-VL-7B")
    plan = _plan(_read_with("mlx-community/Qwen2.5-VL-7B-Instruct-4bit"))
    assert plan["refusals"] == []
    assert plan["workflows"][0]["model_override"] == "mlx-community/Qwen2.5-VL-7B-Instruct-4bit"


@pytest.mark.asyncio
async def test_a_run_that_cannot_be_served_is_refused_before_the_running_server_is_touched(mac):
    """A refusal must never cost the model already loaded."""
    mac.install("Qwen2.5-VL-3B", "mlx-community/Qwen3-VL-8B")
    three = mac.loaded("Qwen2.5-VL-3B")
    with pytest.raises(llm.LocalModelHardwareError, match="24 GB"):
        await llm._ensure_managed_local_provider_ready(
            LLMConfig(provider="omlx", model="mlx-community/Qwen3-VL-8B"), capability="vision")
    with pytest.raises(llm.LocalModelUnavailableError, match="not in Fichero's local model catalogue"):
        await llm._ensure_managed_local_provider_ready(LLMConfig(provider="omlx", model="someone/else"))
    assert three.process.stops == 0 and _served() == "Qwen2.5-VL-3B"
