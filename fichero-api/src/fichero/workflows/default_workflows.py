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


def seed_default_workflows(db: "Database", force: bool = False) -> int:
    """Insert preset workflows into the library.

    Default behaviour: match by workflow name (case-sensitive) and only insert
    missing names. A user who renamed or deleted a preset will not see it
    re-seeded — only truly-missing names are inserted.

    With ``force=True``: delete any existing workflow whose name matches a
    preset AND whose ``is_template`` flag is set, then re-insert from the
    current JSON. Used by the reinstall-defaults action so shipping a new
    preset version (new edges, new nodes, fixed schema) actually reaches
    libraries that already have the old copy. User-duplicated / renamed
    workflows are untouched because only is_template=True rows are deleted.

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

    preset_names = {preset.get("name") for preset in presets if preset.get("name")}
    existing_by_name = {w.name: w for w in existing}

    if force:
        for name in preset_names:
            current = existing_by_name.get(name)
            if current is not None and getattr(current, "is_template", False):
                try:
                    db.delete(current)
                    logger.info(f"Removed stale default workflow '{name}' for reinstall")
                except Exception as exc:
                    logger.warning(f"Could not delete preset '{name}' during reinstall: {exc}")
                existing_by_name.pop(name, None)

    existing_names = set(existing_by_name.keys())
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
