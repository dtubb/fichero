"""A project's chosen embedding model, kept in its package (`search.embedding.chosen-at-project-creation`, #6122).

The model is chosen when the project is created and lives in `embedding.json` beside the database, so it moves with the
package. This module only reads and writes the name; `db.embeddings` maps it to a supported space."""
from __future__ import annotations

import json
from pathlib import Path

from fichero_server.core.atomic_json import write_json_atomic

CHOICE_FILE = "embedding.json"


def read_choice(package: Path | str) -> str | None:
    """The model name the project chose, or None (none chosen, or the file is unreadable: the engine's default stands)."""
    try:
        data = json.loads((Path(package) / CHOICE_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    model = data.get("model") if isinstance(data, dict) else None
    return model.strip() if isinstance(model, str) and model.strip() else None


def write_choice(package: Path | str, model: str) -> None:
    write_json_atomic(Path(package) / CHOICE_FILE, {"model": model})
