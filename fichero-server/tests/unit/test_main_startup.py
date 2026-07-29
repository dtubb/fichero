"""Startup-side effects of fichero_server.api.main.

These are module-level side effects (env vars, warnings filters) that
must be in place before the app handles any request — verified here so
a refactor doesn't silently drop them.
"""

from __future__ import annotations

import os
import sys
import types
import warnings


def test_lance_fork_warning_is_suppressed() -> None:
    """_install_warning_filters() silences lancedb's over-broad "lance
    is not fork-safe" advisory — it fires on every fork (including
    benign subprocess fork+exec) but the engine never
    forks-and-keeps-running-Python with lancedb open. Unrelated
    warnings still surface. (#1028)"""
    from fichero_server.api.main import _install_warning_filters

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        _install_warning_filters()
        warnings.warn(
            "lance is not fork-safe. If you are using multiprocessing, "
            "use spawn instead.",
            UserWarning,
        )
        warnings.warn("an unrelated advisory", UserWarning)

    messages = [str(w.message) for w in caught]
    assert not any("fork-safe" in m for m in messages), (
        "the lance fork-safety warning should be suppressed"
    )
    assert any("unrelated advisory" in m for m in messages), (
        "unrelated warnings must still surface"
    )


def test_tokenizers_parallelism_disabled() -> None:
    """main.py disables the Rust tokenizer thread pool so it can't
    deadlock across a fork. (#1028 context)"""
    import fichero_server.api.main  # noqa: F401 — import triggers the setdefault

    assert os.environ.get("TOKENIZERS_PARALLELISM") == "false"


def test_prewarm_embeddings_honors_bge_m3_env(monkeypatch) -> None:
    """Prewarm must load the same explicit embedding space as the real embedder."""
    from fichero_server.api.main import _prewarm_embeddings
    from fichero_server.llm.local_models import MODELS_BASE

    calls: list[dict] = []
    supported: list[types.SimpleNamespace] = []

    class PoolingType:
        MEAN = "mean"

    class ModelSource:
        def __init__(self, *, hf: str):
            self.hf = hf

    class FakeTextEmbedding:
        def __init__(self, *, model_name: str, cache_dir: str):
            calls.append({"model_name": model_name, "cache_dir": cache_dir})

        @staticmethod
        def _list_supported_models():
            return supported

        @staticmethod
        def list_supported_models():
            return [{"model": model.model} for model in supported]

        @staticmethod
        def add_custom_model(**kwargs):
            supported.append(types.SimpleNamespace(model=kwargs["model"]))

    fake_fastembed = types.ModuleType("fastembed")
    fake_fastembed.__path__ = []
    fake_fastembed.TextEmbedding = FakeTextEmbedding
    fake_common = types.ModuleType("fastembed.common")
    fake_common.__path__ = []
    monkeypatch.setitem(sys.modules, "fastembed", fake_fastembed)
    monkeypatch.setitem(sys.modules, "fastembed.common", fake_common)
    monkeypatch.setitem(
        sys.modules,
        "fastembed.common.model_description",
        types.SimpleNamespace(PoolingType=PoolingType, ModelSource=ModelSource),
    )
    monkeypatch.setenv("FICHERO_EMBED_MODEL", "BAAI/bge-m3")

    _prewarm_embeddings()

    assert calls == [
        {
            "model_name": "BAAI/bge-m3",
            "cache_dir": str(MODELS_BASE / "embeddings"),
        }
    ]
