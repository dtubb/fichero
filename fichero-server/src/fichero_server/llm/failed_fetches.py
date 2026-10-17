"""The model store's record of the last fetch that failed for a repository (`source.recipe.pinned-model-gone`, #5364).

A fetch that fails because the repository is gone or refuses (not a dropped connection, which is tried again) is written to
`failed_fetches.json` in the store's root with its reason, and the entry is removed when the model lands. `check_recipe`
reads it, so the check says a pinned model can no longer be fetched without any network call.
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path

FILE = "failed_fetches.json"
_LOCK = threading.Lock()  # ponytail: one process writes (the engine); a file lock if a second ever does


def _read(root: Path) -> dict[str, str]:
    try:
        data = json.loads((root / FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}


def _write(root: Path, kept: dict[str, str]) -> None:
    """Replace the record whole or not at all: a temporary file beside it, then an atomic replace."""
    root.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=root, prefix=FILE + ".")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(kept, handle, indent=1)
        os.replace(tmp, root / FILE)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def record(root: Path, repo_id: str, reason: str) -> None:
    """Remember why the last fetch of `repo_id` failed."""
    with _LOCK:
        _write(root, {**_read(root), repo_id: reason})


def clear(root: Path, repo_id: str) -> None:
    """Forget the failure of `repo_id`: the model landed."""
    with _LOCK:
        kept = _read(root)
        if kept.pop(repo_id, None) is not None:
            _write(root, kept)


def last(repo_id: str, root: Path | None = None) -> str | None:
    """Why the last fetch of `repo_id` failed, or None; the store's own root unless one is given."""
    if root is None:
        from fichero_server.llm.mlx_model_store import mlx_model_store_dir

        root = mlx_model_store_dir()
    return _read(root).get(repo_id)
