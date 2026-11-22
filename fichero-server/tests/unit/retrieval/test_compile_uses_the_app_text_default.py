"""The model that turns a question into a search is the app's text default, like chat's, and an engine run from
source finds the on-device bridge where the build puts it (#6791, `search.ask.uses-the-chosen-text-model`)."""

from __future__ import annotations

from pathlib import Path

from fichero_server import llm
from fichero_server.retrieval.query_compiler import _resolve_compiler_config


class _AppDB:
    def __init__(self, defaults: dict[str, str]) -> None:
        self._defaults = defaults

    def get_ai_defaults(self) -> dict[str, str]:
        return self._defaults


def test_the_compiler_uses_the_provider_and_model_chosen_in_settings(db, monkeypatch) -> None:
    monkeypatch.setattr(
        "fichero_server.db.app.get_app_db",
        lambda: _AppDB({"default_text_provider": "ollama", "default_text_model": "llama3.2"}),
    )

    config = _resolve_compiler_config(db)

    assert (config.provider, config.model) == ("ollama", "llama3.2")
    assert config.temperature == 0.0


def test_an_empty_default_stays_on_the_device(db, monkeypatch) -> None:
    monkeypatch.setattr("fichero_server.db.app.get_app_db", lambda: _AppDB({}))

    config = _resolve_compiler_config(db)

    assert (config.provider, config.model) == ("apple", "apple-intelligence")


def test_a_source_run_looks_for_the_bridge_in_the_engine_folder() -> None:
    engine_folder = Path(llm.__file__).resolve().parents[3]
    assert engine_folder.name == "fichero-server"

    candidate = llm._fm_bridge_candidates()[2]

    assert candidate == engine_folder / "bin" / "fm-bridge" / "fm-bridge"
    assert candidate.parent.is_dir()
