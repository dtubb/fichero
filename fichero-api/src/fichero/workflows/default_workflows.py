"""
Default workflow seeding.

Ships a small set of preset workflows (currently Transcribe and Catalogue)
that appear automatically in a fresh library. Users can edit, duplicate, or
delete them like any other workflow; deleting doesn't re-seed, so the
experience matches Finder's "Documents" folder rather than a sync.

Seeding is called from ``DatabaseManager.get_database`` after migrations run,
so every library gets the presets on its first open in a new code version
without requiring an explicit "install templates" action.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fichero.db import Database

logger = logging.getLogger(__name__)


_PRESETS_DIR = Path(__file__).resolve().parent.parent / "resources" / "default_workflows"


def _load_preset_files() -> list[dict]:
    """Read every *.json preset in the resources/default_workflows directory."""
    if not _PRESETS_DIR.is_dir():
        logger.warning(f"Default workflows dir not found: {_PRESETS_DIR}")
        return []

    presets: list[dict] = []
    for path in sorted(_PRESETS_DIR.glob("*.json")):
        try:
            with path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict) and data.get("name"):
                presets.append(data)
        except Exception as exc:
            logger.warning(f"Failed to load preset {path.name}: {exc}")
    return presets


def seed_default_workflows(db: "Database") -> int:
    """Insert preset workflows into the library if they don't already exist.

    Matching is by workflow name (case-sensitive). A user who renames or
    deletes a preset will not see it re-seeded — only truly-missing names
    are inserted.

    Returns the number of workflows newly seeded.
    """
    from fichero.models import Workflow

    presets = _load_preset_files()
    if not presets:
        return 0

    try:
        existing = list(db.all(Workflow))
    except Exception as exc:
        logger.warning(f"seed_default_workflows: cannot list workflows: {exc}")
        return 0

    existing_names = {w.name for w in existing}
    seeded = 0

    for preset in presets:
        name = preset.get("name")
        if not name or name in existing_names:
            continue

        try:
            workflow = Workflow(
                name=name,
                description=preset.get("description", ""),
                format=preset.get("format", "nodes"),
                is_template=bool(preset.get("is_template", True)),
                folder_path=preset.get("folder_path", "/"),
                tags=list(preset.get("tags", [])),
                steps=list(preset.get("steps", [])),
                nodes=list(preset.get("nodes", [])),
                edges=list(preset.get("edges", [])),
                config=dict(preset.get("config", {})),
                provider=preset.get("provider", ""),
                model=preset.get("model", ""),
            )
            db.save(workflow)
            seeded += 1
            logger.info(f"Seeded default workflow: {name}")
        except Exception as exc:
            logger.error(f"Failed to seed preset '{name}': {exc}")

    return seeded
