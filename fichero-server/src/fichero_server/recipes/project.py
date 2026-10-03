"""A project's setup answers and recipe, kept as files in the project folder (#4951).

`source/models-chains-and-projects.md`: `source.project.has-settings` (purpose, recipe, defaults)
and `source.recipe.folder-format`. The project folder holds `recipe/recipe.yaml` (the recipe, the
shareable format) and `recipe/setup.yaml` (setup's answers, so the person can come back to them).
Files, not database rows: they travel with the project, a person can read them, and the recipe is
already in the form it is shared in. A project never set up has neither file and behaves exactly
as before. Nothing here runs anything: saving is not Start (`source.project.automatic-after-first-yes`).
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

from fichero_server.recipes.recipe import _walk_forbidden

FOLDER = "recipe"
_FILES = {"recipe": "recipe.yaml", "answers": "setup.yaml"}


def _path(library: Path, part: str) -> Path:
    return Path(library) / FOLDER / _FILES[part]


def read_project_setup(library: Path) -> dict[str, Any]:
    """`{"answers": ..., "recipe": ...}`, each None when the project has not saved one."""
    import yaml

    out: dict[str, Any] = {}
    for part in _FILES:
        path = _path(library, part)
        out[part] = yaml.safe_load(path.read_text(encoding="utf-8")) if path.is_file() else None
    return out


def write_project_setup(library: Path, answers: dict | None, recipe: dict | None) -> None:
    """Save (or, with None, remove) the answers and the recipe. Refuses code or credentials in
    either: a recipe is data and names providers, never keys."""
    problems: list[str] = []
    # Setup's answers name writing systems at their top level (`scripts`), as a recipe's `suits` does.
    _walk_forbidden(answers, "answers.", "suits", problems)
    _walk_forbidden(recipe, "recipe.", "", problems)
    if problems:
        raise ValueError("; ".join(problems))
    for part, value in (("answers", answers), ("recipe", recipe)):
        path = _path(library, part)
        if value is None:
            path.unlink(missing_ok=True)
            continue
        _write_yaml(path, value)


def _write_yaml(path: Path, value: Any) -> None:
    import yaml

    path.parent.mkdir(parents=True, exist_ok=True)
    # Written whole or not at all: a crash never leaves half a recipe.
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        yaml.safe_dump(value, fh, sort_keys=False, allow_unicode=True)
    os.replace(tmp, path)


#: The first yes (`source.project.automatic-after-first-yes`): when Start was pressed and on which
#: recipe version. Its absence means nothing in this project runs by itself.
START_FILE = "started.yaml"


def read_start(library: Path) -> dict[str, Any] | None:
    import yaml

    path = Path(library) / FOLDER / START_FILE
    return yaml.safe_load(path.read_text(encoding="utf-8")) if path.is_file() else None


def write_start(library: Path, record: dict[str, Any] | None) -> None:
    """Record (or, with None, withdraw) the first yes."""
    path = Path(library) / FOLDER / START_FILE
    if record is None:
        path.unlink(missing_ok=True)
    else:
        _write_yaml(path, record)
