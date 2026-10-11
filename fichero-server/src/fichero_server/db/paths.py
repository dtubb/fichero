"""Canonical engine storage paths and one-time legacy migration."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

_LEGACY_APP_SUPPORT_DIRS = (
    ("com.fichero.fichero",),
    ("ca.tubb.fichero", "global.fichero"),
    # The SwiftUI app historically wrote the global library under its bundle id
    # (~/Library/Application Support/app.fichero.fichero/) — migrate it into the
    # canonical Fichero/ dir so all data lives in one place (#1526).
    ("app.fichero.fichero",),
)


GLOBAL_LIBRARY_PACKAGE_NAME = "global.fichero"


#: The one setting root for every engine-owned file (#5530): app.duckdb, global.fichero, the model
#: stores, job dirs, caches. Unset in the shipped app and the dev engine, so they keep the default
#: below; a test run or a harness engine sets it to a temp dir and nothing of the person's is touched.
BASE_PATH_ENV = "FICHERO_BASE_PATH"
#: Where the model stores (models/, kraken-models/, mlx-runtime/) live, when not under the base.
#: An explicit opt-in for a harness engine that should use the models this machine already has
#: (the acceptance engine, the integration engines' shared cache) -- never set by the app.
MODEL_STORE_ROOT_ENV = "FICHERO_MODEL_STORE_ROOT"


def default_server_state_dir(home: Path | None = None) -> Path:
    """Where the shipped app and the dev engine keep their state: ~/Library/Application Support/Fichero."""
    base_home = home or Path.home()
    return base_home / "Library" / "Application Support" / "Fichero"


def server_state_dir(home: Path | None = None) -> Path:
    """The engine's state root: ``$FICHERO_BASE_PATH`` when set, else the default.

    An explicit ``home`` names a home directory and always means the default layout under it.
    """
    if home is None:
        override = os.environ.get(BASE_PATH_ENV, "").strip()
        if override:
            return Path(override)
    return default_server_state_dir(home)


def model_store_root(home: Path | None = None) -> Path:
    """The parent of the model stores: ``$FICHERO_MODEL_STORE_ROOT`` when set, else the state root."""
    if home is None:
        override = os.environ.get(MODEL_STORE_ROOT_ENV, "").strip()
        if override:
            return Path(override).expanduser()
    return server_state_dir(home)


# Every Hugging Face download and lookup lands in Fichero's own model store (`runtime.models-in-the-store`, ruled
# 2026-10-11: Daniel found 4.2 GB of the TrOCR reader tridis in ~/.cache/huggingface, where a `from_pretrained` with
# no cache_dir had put it). Each load names `hf_hub_dir()`; and at engine start (`fichero_server/__init__.py`, the
# first module uvicorn and the embedded engine both import, before any Hugging Face library reads them) the cache
# variables point into the store unless already set, so no library falls back to ~/.cache by itself. Here, not in a
# module of their own, so the engine's import budget (#3950) pays nothing for them.
HF_CACHE_ENV = {"HF_HOME": "", "HF_HUB_CACHE": "hub", "TRANSFORMERS_CACHE": "hub",
                "SENTENCE_TRANSFORMERS_HOME": "sentence-transformers"}


def hf_store_dir() -> Path:
    """Fichero's own Hugging Face folder: `model_store_root()/models/hf`."""
    return model_store_root() / "models" / "hf"


def hf_hub_dir() -> Path:
    """Where a Hugging Face model is downloaded and found: the `cache_dir` every load in the engine names."""
    return hf_store_dir() / "hub"


def pin_hf_caches() -> dict[str, str]:
    """Point the Hugging Face cache variables into the store, each unless already set. Returns them as they stand."""
    root = hf_store_dir()
    for name, sub in HF_CACHE_ENV.items():
        if not os.environ.get(name, "").strip():
            os.environ[name] = str(root / sub) if sub else str(root)
    return {name: os.environ[name] for name in HF_CACHE_ENV}


def is_global_library_package(package_path: Path | str) -> bool:
    """Whether this package is the engine's global library.

    Matched by package NAME rather than by comparing against
    ``settings.global_library_path`` because the global library lives under
    ``Path.home()``, and the app's home differs between a sandboxed (App
    Store) container and an unsandboxed build — a path comparison would call
    the container's own ``global.fichero`` a normal library. The name is the
    stable identity across both.
    """
    return Path(package_path).name == GLOBAL_LIBRARY_PACKAGE_NAME


def migrate_legacy_server_state(home: Path | None = None) -> int:
    """Move legacy engine state trees into the canonical Fichero directory."""
    base_home = home or Path.home()
    app_support = base_home / "Library" / "Application Support"
    target = server_state_dir(base_home)
    target.mkdir(parents=True, exist_ok=True)

    migrated_entries = 0
    for legacy_parts in _LEGACY_APP_SUPPORT_DIRS:
        legacy_root = app_support.joinpath(*legacy_parts)
        if not legacy_root.exists() or legacy_root == target:
            continue
        for entry in legacy_root.iterdir():
            dest = target / entry.name
            if dest.exists():
                continue
            shutil.move(str(entry), str(dest))
            migrated_entries += 1
    return migrated_entries

