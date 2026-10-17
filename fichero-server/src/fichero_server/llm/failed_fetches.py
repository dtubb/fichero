"""The model store's record of the last fetch that failed for a repository (`source.recipe.pinned-model-gone`, #5364).

A fetch that fails because the repository is gone or refuses (not a dropped connection, which is tried again) is written to
`failed_fetches.json` in the store's root with its reason, and the entry is removed when the model lands. `check_recipe`
reads it, so the check says a pinned model can no longer be fetched without any network call.
"""
from __future__ import annotations

import json
from pathlib import Path

FILE = "failed_fetches.json"


def _read(root: Path) -> dict[str, str]:
    try:
        data = json.loads((root / FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}


def record(root: Path, repo_id: str, reason: str) -> None:
    """Remember why the last fetch of `repo_id` failed."""
    root.mkdir(parents=True, exist_ok=True)
    (root / FILE).write_text(json.dumps({**_read(root), repo_id: reason}, indent=1), encoding="utf-8")


def clear(root: Path, repo_id: str) -> None:
    """Forget the failure of `repo_id`: the model landed."""
    kept = _read(root)
    if kept.pop(repo_id, None) is not None:
        (root / FILE).write_text(json.dumps(kept, indent=1), encoding="utf-8")


def last(repo_id: str, root: Path | None = None) -> str | None:
    """Why the last fetch of `repo_id` failed, or None; the store's own root unless one is given."""
    if root is None:
        from fichero_server.llm.mlx_model_store import mlx_model_store_dir

        root = mlx_model_store_dir()
    return _read(root).get(repo_id)
