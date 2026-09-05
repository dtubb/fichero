"""Guard: embedded local models (Apple FM + MLX) stay lean (#2615).

Requirement: ship BOTH on-device backends — Apple Foundation Models
(subprocess to the Swift fm-bridge) and MLX (a separate mlx-lm server spoken
to over HTTP via langchain-openai) — *without* dragging torch/transformers
into the shipped engine.

The "without heavy deps" half was previously enforced only by comments in
pyproject.toml. These tests make it executable: if a future change adds a
torch-class dependency to a *shipped* list, this fails loudly instead of
silently bloating the bundle by hundreds of MB.

AMENDED 2026-09-04: spaCy ships, by ruling. The guard was right to fire on it
and its premise was wrong — the rule is about the hundreds-of-MB class, and
spaCy's whole tier is ~54 MB measured. The exemption is a NAMED list of three
packages, not a category, and the heavy exclusions it sits beside are now
asserted by name so this amendment cannot be read as a general relaxation.
See `_ALLOWED_BY_RULING`.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
import sys

import pytest

# Heavy ML stacks that must never enter the shipped engine. MLX is the light
# Apple-Silicon path and runs as its own mlx-lm *server* process (HTTP), so
# even mlx-lm/mlx-vlm must not be imported into the engine.
#
# THE RULE IS ABOUT SIZE, NOT ABOUT THE WORD "ML". Every name here costs
# hundreds of megabytes — torch and its dependents, pykeen (which is torch),
# OpenCV. That is the class #2615 was written to keep out, and those
# exclusions are unchanged and asserted below.
_FORBIDDEN_SHIPPED = {
    "torch",
    "torchvision",
    "transformers",
    "sentence-transformers",
    "accelerate",
    "pykeen",
    "mlx",
    "mlx-lm",
    "mlx-vlm",
    "opencv-python",
    "opencv-python-headless",
}

# PREMISE CHANGED 2026-09-04, by ruling, not by erosion.
#
# spaCy was on the forbidden list on the assumption that it belonged to the
# same size class. It does not: measured, the runtime is 38 MB and each small
# model 15-16 MB — ~54 MB for the whole tier, an order of magnitude under
# pykeen/torch. And it earns its place: it is the SVO grammar gate, which
# convicts a predicate that is not a verb and a first-person verb stamped with
# a bystander's name — 16 of the 17 rows a real extraction left in a test
# library. Apple's on-device NLTagger cannot replace it (it exposes no
# morphology for Spanish at all), so without the bundle the shipped app ran
# that gate on half power, silently.
#
# Daniel ruled it in. This list is the ONLY thing that may enter the bundle on
# that ruling — named exactly, versions and all, so "spaCy is allowed" cannot
# quietly become "spaCy plus whatever else someone adds next".
_ALLOWED_BY_RULING = {
    "spacy",
    "es_core_news_sm",
    "en_core_web_sm",
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
    briefcase = data["tool"]["briefcase"]["app"]["fichero_server"]
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


def test_the_heavy_class_is_still_excluded_by_name():
    """The premise change must not have relaxed the rule it sits inside.

    spaCy entering the bundle is a ruling about ~54 MB. It is not a precedent
    for the hundreds-of-MB class, and the easiest way for that to erode is for
    someone to read "the leanness guard allows an ML package now" and stop
    there. These names stay forbidden, explicitly.
    """
    for heavy in ("torch", "pykeen", "transformers", "opencv-python-headless"):
        assert heavy in _FORBIDDEN_SHIPPED, heavy
    assert not (_FORBIDDEN_SHIPPED & _ALLOWED_BY_RULING), (
        "a package cannot be both forbidden and allowed by ruling"
    )


def test_only_the_ruled_in_packages_use_the_exemption():
    """Nothing rides in beside spaCy.

    The exemption is a named list, not a category. `es_core_news_lg` (568 MB)
    is deliberately absent from it: it carries word vectors this gate does not
    use, and its benefit for 16th-century orthography is unmeasured, so it
    stays a catalog row someone downloads rather than weight everyone carries.
    """
    shipped = {
        _base_name(r)
        for values in _shipped_lists().values()
        for r in values
    }
    assert "es_core_news_lg" not in shipped
    # Every exemption is USED. An entry nobody ships is a permission sitting
    # unspent, and the next person to need one finds it already granted.
    assert _ALLOWED_BY_RULING <= shipped, sorted(_ALLOWED_BY_RULING - shipped)


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
    """The stanza must name the package that EXISTS, and ship resources/bin.

    This test used to read ``package-data["fichero"]`` — and passed, because
    the stanza said "fichero" too. Both were four months stale: the package
    became ``fichero_server`` in #2566, so setuptools matched nothing and the
    fm-bridge binary, the workflow presets and the meta manifests were left
    out of any wheel built from this project (2026-09-02). A test that
    hard-codes the same wrong key as the code cannot see that.

    So assert the KEY against the real package name rather than a literal.
    Nothing here needs a built fm-bridge on disk: the binary is gitignored, so
    requiring it would fail in every fresh worktree while saying nothing about
    the packaging contract, which is what this guards.
    """
    data = _pyproject()
    package_data = data["tool"]["setuptools"]["package-data"]

    package_name = data["project"]["name"].replace("-", "_")
    assert package_name in package_data, (
        f"package-data is keyed {sorted(package_data)}, but the package is "
        f"{package_name!r} — setuptools matches nothing and ships no resources"
    )
    assert "resources/bin/*" in package_data[package_name], (
        "resources/bin/* is not shipped; the fm-bridge binary would be absent "
        "from the wheel"
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
