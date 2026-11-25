"""The harness.toml values a second client sets (builder.client.*). Every default is the literal Fichero ran with before the
hook existed, so a rules file that names none of them changes nothing."""

from __future__ import annotations

import tomllib
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent


def _doc(root) -> dict:
    """root's harness.toml; no root = no file: a caller names a trusted root (--root, the pinned copy), never the start directory,
    which a jailed worker owns."""
    if root is None:
        return {}
    f = Path(root) / "harness.toml"
    return tomllib.loads(f.read_text()) if f.is_file() else {}


def _get(root, table: str, key: str, default):
    return _doc(root).get(table, {}).get(key, default)


def land_repo(root=None) -> str:
    """[land].repo: the `owner/name` gh talks to."""
    return _get(root, "land", "repo", "dtubb/fichero")


def land_branch(root=None) -> str:
    """[land].branch: where finished work lands."""
    return _get(root, "land", "branch", "integration")


def release_branch(root=None) -> str:
    """[land].release_branch: the branch a release merges to; "" = no release branch, no main/PR logic."""
    return _get(root, "land", "release_branch", "main")


def product(root=None) -> str:
    """[policy].product: the last words of the commit trailer."""
    return _get(root, "policy", "product", "Fichero Builder")


def harness_name(root=None) -> str:
    return _get(root, "harness", "name", "fichero")


def state_env(root=None) -> str:
    """The environment variable that names the state directory: FICHERO_BUILDER_STATE for the default name."""
    return f"{harness_name(root).upper()}_BUILDER_STATE"


def label_prefix(root=None) -> str:
    """The launchd label prefix of the loop, console and release agents."""
    return _get(root, "harness", "label_prefix", "local.builder")


def scripts_dir(root=None) -> Path:
    """[harness].scripts_dir: where harness_*.py live (default: the checkout holding this package)."""
    v = _get(root, "harness", "scripts_dir", "")
    return (Path(root) / v) if v else PACKAGE.parents[1] / "scripts"  # a relative value is relative to root; an absolute one wins


def script(root, name: str, default: Path) -> Path:
    """`name` in root's [harness].scripts_dir when it sets one, else `default` (a module's own constant, which tests may point elsewhere)."""
    return scripts_dir(root) / name if _get(root, "harness", "scripts_dir", "") else default


def package_dir(root=None) -> str:
    """[harness].package_dir: the builder package's path inside a pinned copy."""
    return _get(root, "harness", "package_dir", "fichero-builder/fichero_builder")
