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
            if current is not None and (
                getattr(current, "is_template", False) or getattr(current, "is_system", False)
            ):
                try:
                    db.delete(current)
                    logger.info(f"Removed stale default workflow '{name}' for reinstall")
                except Exception as exc:
                    logger.warning(f"Could not delete preset '{name}' during reinstall: {exc}")
                existing_by_name.pop(name, None)

    existing_names = set(existing_by_name.keys())
    seeded = 0

    # Resolve the built-in Apple Intelligence provider's id (if it exists)
    # so presets can reference it via the "$APPLE_INTELLIGENCE" sentinel.
    # Done once per seed call rather than per node. The Apple provider has
    # a runtime-generated UUID so presets can't hardcode it directly —
    # the sentinel + late-binding resolves to the actual id at install time.
    apple_provider_id = _resolve_apple_intelligence_id()

    for preset in presets:
        name = preset.get("name")
        if not name or name in existing_names:
            continue

        try:
            nodes = _expand_provider_sentinels(
                list(preset.get("nodes", [])),
                apple_provider_id=apple_provider_id,
            )
            workflow = Workflow(
                name=name,
                description=preset.get("description", ""),
                format=preset.get("format", "nodes"),
                is_template=bool(preset.get("is_template", True)),
                is_system=bool(preset.get("is_system", False)),
                folder_path=preset.get("folder_path", "/"),
                tags=list(preset.get("tags", [])),
                steps=list(preset.get("steps", [])),
                nodes=nodes,
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


def _resolve_apple_intelligence_id() -> str | None:
    """Look up the runtime UUID of the built-in Apple Intelligence provider
    so presets that reference '$APPLE_INTELLIGENCE' as a sentinel can be
    rewritten to the real id at seed time. Returns None if the provider
    isn't available (non-macOS dev install, seeding before _seed_builtin_providers
    has run, etc.) — in that case nodes keep the sentinel and the user picks
    a provider manually.
    """
    try:
        from fichero.app_db import get_app_db
        from fichero.models import ProviderType
        app_db = get_app_db()
        for provider in app_db.list_providers():
            if provider.provider_type == ProviderType.apple:
                return provider.id
    except Exception as exc:
        logger.warning(f"Apple Intelligence id lookup failed: {exc}")
    return None


def _expand_provider_sentinels(
    nodes: list[dict],
    apple_provider_id: str | None,
) -> list[dict]:
    """Replace '$APPLE_INTELLIGENCE' sentinel in each node's provider_name
    with the resolved Apple Intelligence provider id. Sentinel comes from
    preset JSON (catalogue_apple_vision.json) so the on-device workflow
    pre-selects Apple Intelligence on every LLM node out of the box.
    """
    if not apple_provider_id:
        # No Apple provider seeded yet — leave sentinel; the workflow will
        # show "Select provider..." and the user picks Apple Intelligence
        # manually after launch (still better than today: at least the user
        # knows which provider to pick).
        return nodes
    expanded = []
    for node in nodes:
        if isinstance(node, dict) and node.get("provider_name") == "$APPLE_INTELLIGENCE":
            new_node = dict(node)
            new_node["provider_name"] = apple_provider_id
            expanded.append(new_node)
        else:
            expanded.append(node)
    return expanded
