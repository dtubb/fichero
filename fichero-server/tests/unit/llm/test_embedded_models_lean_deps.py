"""Guard: embedded local models (Apple FM + MLX) stay lean (#2615).

Requirement: ship BOTH on-device backends — Apple Foundation Models
(subprocess to the Swift fm-bridge) and MLX (a separate mlx-lm server spoken
to over HTTP via langchain-openai) — *without* dragging torch/transformers
into the shipped engine.

The "without heavy deps" half was previously enforced only by comments in
pyproject.toml. These tests make it executable: if a future change adds a
torch-class dependency to a *shipped* list, this fails loudly instead of
silently bloating the bundle by hundreds of MB.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
import sys

import pytest

# Heavy ML stacks that must never enter the shipped engine. MLX is the light
# Apple-Silicon path and runs as its own mlx-lm *server* process (HTTP), so
# even mlx-lm/mlx-vlm must not be imported into the engine.
_FORBIDDEN_SHIPPED = {
    "torch",
    "torchvision",
    "transformers",
    "sentence-transformers",
    "accelerate",
    "pykeen",
    "spacy",
    "mlx",
    "mlx-lm",
    "mlx-vlm",
    "opencv-python",
    "opencv-python-headless",
}


def _pyproject() -> dict:
    root = Path(__file__).resolve().parents[3]  # fichero-server/
    with open(root / "pyproject.toml", "rb") as fh:
        return tomllib.load(fh)


def _base_name(requirement: str) -> str:
    """Strip version/extras: 'uvicorn[standard]>=1' -> 'uvicorn'."""
    name = requirement.strip()
    for sep in ("[", ">", "<", "=", "!", "~", ";", " "):
        name = name.split(sep, 1)[0]
    return name.strip().lower()


def _shipped_lists() -> dict[str, list[str]]:
    """The dependency lists that actually ship in the bundle.

    Deliberately EXCLUDES [project.optional-dependencies] (kg/image/dev) —
    those are local-dev extras where torch-class deps are allowed.
    """
    data = _pyproject()
    # #4227 renamed the briefcase app key engine -> server.
    briefcase = data["tool"]["briefcase"]["app"]["server"]
    return {
        "briefcase.requires": briefcase.get("requires", []),
        "project.dependencies": data["project"]["dependencies"],
    }


@pytest.mark.parametrize("list_name", ["briefcase.requires", "project.dependencies"])
def test_shipped_deps_have_no_heavy_ml(list_name):
    names = {_base_name(r) for r in _shipped_lists()[list_name]}
    leaked = names & _FORBIDDEN_SHIPPED
    assert not leaked, (
        f"{list_name} ships heavy ML deps {sorted(leaked)} — #2615 requires "
        "Apple FM (subprocess) and MLX (separate mlx-lm server over HTTP) to "
        "stay out of the engine bundle. Move it to optional-dependencies."
    )


def test_apple_and_mlx_providers_are_registered_local():
    """Both on-device backends are selectable and marked local/private."""
    from fichero_server.llm.providers import PROVIDERS, ProviderType

    apple = PROVIDERS[ProviderType.apple]
    assert apple.is_local, "Apple FM must be marked local (zero cloud calls)"

    # MLX ships as the OpenAI-compatible 'omlx' provider (a local mlx-lm server).
    omlx = PROVIDERS[ProviderType.omlx]
    assert omlx.is_local, "MLX (omlx) must be marked local (on-device server)"


def test_mlx_provider_uses_local_openai_compatible_base_url():
    """omlx (MLX) talks to a localhost OpenAI-compatible server, keyless."""
    from fichero_server.llm import _KEYLESS_OPENAI_COMPATIBLE, _OPENAI_COMPATIBLE_BASE_URLS

    assert "omlx" in _OPENAI_COMPATIBLE_BASE_URLS
    base = _OPENAI_COMPATIBLE_BASE_URLS["omlx"]
    assert "localhost" in base or "127.0.0.1" in base, base
    assert "omlx" in _KEYLESS_OPENAI_COMPATIBLE


def test_mlx_runtime_targets_separate_prefix(tmp_path, monkeypatch):
    from fichero_server.llm.mlx_runtime import mlx_runtime_dir

    runtime_dir = tmp_path / "Fichero" / "mlx-runtime"
    monkeypatch.setenv("FICHERO_MLX_RUNTIME_DIR", str(runtime_dir))

    resolved = mlx_runtime_dir()
    assert resolved == runtime_dir
    assert resolved != Path(sys.prefix)
    assert resolved not in Path(sys.prefix).parents


def test_package_data_includes_fm_bridge_binary():
    data = _pyproject()
    package_data = data["tool"]["setuptools"]["package-data"]["fichero"]
    assert "resources/bin/*" in package_data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
