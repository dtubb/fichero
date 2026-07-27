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

# Legacy preset names that should be silently retired when present as
# system/template rows. These variants were removed from shipped JSON but
# can remain in existing libraries from older versions.
_DEPRECATED_PRESET_NAMES: set[str] = {
    "Catalogue (composable)",
    "Catalogue (Apple Vision)",
    "Catalogue Full Pipeline",
    "Catalogue Each",
    "Catalogue Stage 1 - Transcribe Pages",
    "Catalogue Stage 2 - Extract Entities + KG",
    "Catalogue Stage 3 - Catalogue Artifacts",
    "Transcribe (Apple Vision)",
    # Merged into "Transcribe Spanish Script (19th-20th C.)" (#2251)
    "Transcribe Spanish Script (19th-20th C., Multi-Pass)",
    "Transcribe Spanish Script v2 (19th-20th C., Sub-Workflow)",
    # Merged into "Transcribe Paleography" (language=auto) (#2251)
    "Spanish Paleography (18th–19th C.)",
}


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

    # Auto-upgrade: any preset whose JSON declares a higher
    # config.preset_version than the stored copy gets force-replaced even
    # when force=False. Lets bug-fix releases (e.g. broken edge wiring,
    # #836) reach existing libraries without the user having to click
    # "Reinstall defaults". User-renamed copies are still skipped because
    # only is_template/is_system rows are touched.
    upgrade_names: set[str] = set()
    presets_by_name = {p.get("name"): p for p in presets if p.get("name")}
    for name, current in list(existing_by_name.items()):
        preset = presets_by_name.get(name)
        if preset is None:
            continue
        if not (getattr(current, "is_template", False) or getattr(current, "is_system", False)):
            continue
        preset_v = (preset.get("config") or {}).get("preset_version", 1)
        stored_v = (getattr(current, "config", None) or {}).get("preset_version", 1)
        if preset_v > stored_v:
            upgrade_names.add(name)

    # One-way cleanup for known deprecated shipped variants (e.g.
    # "Catalogue (composable)") so old libraries stop surfacing stale
    # presets whose graph no longer matches the canonical defaults.
    # Keep this outside force=True so regular app opens heal old installs.
    for name in _DEPRECATED_PRESET_NAMES:
        current = existing_by_name.get(name)
        if current is None:
            continue
        if not (getattr(current, "is_template", False) or getattr(current, "is_system", False)):
            continue
        try:
            db.delete(current)
            logger.info(f"Removed deprecated default workflow '{name}'")
            existing_by_name.pop(name, None)
        except Exception as exc:
            logger.warning(f"Could not remove deprecated preset '{name}': {exc}")

    targets_to_replace: set[str] = preset_names if force else upgrade_names
    for name in targets_to_replace:
        current = existing_by_name.get(name)
        if current is not None and (
            getattr(current, "is_template", False) or getattr(current, "is_system", False)
        ):
            try:
                db.delete(current)
                if name in upgrade_names and not force:
                    logger.info(f"Upgrading preset '{name}' (preset_version bumped)")
                else:
                    logger.info(f"Removed stale default workflow '{name}' for reinstall")
            except Exception as exc:
                logger.warning(f"Could not delete preset '{name}' during reinstall: {exc}")
            existing_by_name.pop(name, None)

    if force:
        # Also prune is_template workflows whose names are NO LONGER in the
        # preset set (i.e. variants that used to ship but were deleted —
        # e.g. 'Catalogue (Apple Vision)' / 'Transcribe (Apple Vision)' /
        # 'Catalogue (composable)' after the architecture moved to a single
        # preset per workflow + runtime model picker). Without this prune,
        # users keep seeing stale variants in the toolbar Run menu after
        # an app update because the seeder only ever INSERTED new names.
        orphaned = []
        for name, wf in existing_by_name.items():
            if name in preset_names:
                continue
            if getattr(wf, "is_template", False) or getattr(wf, "is_system", False):
                orphaned.append((name, wf))
        for name, wf in orphaned:
            try:
                db.delete(wf)
                logger.info(f"Pruned orphaned default workflow '{name}' (no preset file)")
                existing_by_name.pop(name, None)
            except Exception as exc:
                logger.warning(f"Could not prune orphaned preset '{name}': {exc}")

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
    """Resolve the sentinel '$APPLE_INTELLIGENCE' to the id the Swift
    workflow editor uses when comparing node.provider_name to the
    /api/chat/providers list.

    Important: the chat/providers endpoint returns provider TYPES as IDs
    for built-in providers (id="apple"), NOT the actual app_db UUIDs.
    So the resolved sentinel must be the provider_type string, not
    Provider.id from app_db. (A round-trip mismatch exposed this —
    inspecting workflow DB showed UUID, but popover lookup never matched
    because providers list returns "apple".)

    Returns None if Apple Intelligence isn't enabled in app_db so the
    sentinel survives in the preset and the user picks manually.
    """
    try:
        from fichero.db.app import get_app_db
        from fichero.models import ProviderType
        app_db = get_app_db()
        for provider in app_db.list_providers():
            if provider.provider_type == ProviderType.apple:
                # Return the provider_type ENUM VALUE — that's what the
                # chat/providers endpoint exposes as the provider id.
                return ProviderType.apple.value  # "apple"
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


def heal_default_workflow_tree(db: "Database") -> int:
    """Re-home preset workflow mirrors under the locked container (#4102).

    Libraries seeded before the "Default Workflows" container existed hold
    the preset folders (Transcribe, Convert, …) as ROOT-level folder
    documents with the workflow mirrors parented to them — and because
    seeding is idempotent BY NAME it never re-saves those rows, so the
    stale tree survives every launch. Heal explicitly:

    1. Re-save every preset workflow (matched by name, only is_system /
       is_template rows). The mirror save recomputes the parent, placing
       the node under the container's per-folder subfolder. Legacy rows
       that predate the ``is_system`` flag get it set first — every
       shipped preset declares it true.
    2. Delete legacy ROOT-level folders whose name matches a preset
       folder segment and that are left EMPTY. A folder with any child
       (e.g. a user's own "Books" with documents) is never touched.

    Mirrors already homed under the container are skipped, so the steady
    state costs one Workflow list + one Document query per open.
    """
    from fichero.db import _DEFAULT_WORKFLOWS_CONTAINER_ID
    from fichero.models import DocType, Document, Workflow

    presets = _load_preset_files()
    preset_names = {preset.get("name") for preset in presets if preset.get("name")}
    folder_segments = {
        seg
        for preset in presets
        for seg in (preset.get("folder_path") or "/").split("/")
        if seg
    }
    if not preset_names:
        return 0

    try:
        existing = list(db.all(Workflow))
    except Exception as exc:
        logger.warning(f"heal_default_workflow_tree: cannot list workflows: {exc}")
        return 0

    preset_by_name = {p.get("name"): p for p in presets if p.get("name")}
    healed = 0
    for workflow in existing:
        if workflow.name not in preset_names:
            continue
        # Legacy seeded rows PREDATE the is_system/is_template flags, so
        # gating on the flags alone skipped exactly the mirrors this heal
        # was written for (Daniel, live 2026-07-27: preset folders stuck at
        # the tree root forever). A row also counts as seeded when it
        # carries the preset's folder_path — that's what seeding stamps.
        # A user's own same-named workflow (no flags, no preset
        # folder_path) is never touched.
        preset = preset_by_name[workflow.name]
        flagged = getattr(workflow, "is_template", False) or getattr(workflow, "is_system", False)
        looks_seeded = (getattr(workflow, "folder_path", None) or "/") == (
            preset.get("folder_path") or "/"
        )
        if not (flagged or looks_seeded):
            continue
        mirror = db.get(Document, workflow.id)
        parent_id = getattr(mirror, "parent_id", None) if mirror is not None else None
        if parent_id is not None and parent_id.startswith(_DEFAULT_WORKFLOWS_CONTAINER_ID):
            continue  # already homed
        try:
            workflow.is_system = True
            db.save(workflow)
            healed += 1
        except Exception as exc:
            logger.warning(f"Could not re-home preset '{workflow.name}': {exc}")

    # Sweep legacy root-level preset folders that the re-homing emptied.
    try:
        for doc in list(db.query(Document, parent_id=None)):
            if doc.id == _DEFAULT_WORKFLOWS_CONTAINER_ID:
                continue
            if getattr(doc, "doc_type", None) != DocType.folder:
                continue
            if doc.name not in folder_segments:
                continue
            if db.query(Document, parent_id=doc.id):
                continue  # still has content — user's own folder, leave it
            db.delete(doc)
            logger.info(f"Removed empty legacy preset folder '{doc.name}' from root")
    except Exception as exc:
        logger.warning(f"heal_default_workflow_tree: folder sweep failed: {exc}")

    if healed:
        logger.info(f"Re-homed {healed} preset workflow(s) under Default Workflows")
    return healed


def prune_default_workflows(db: "Database") -> int:
    """Remove system-seeded preset workflows from a NON-global library.

    Default workflows belong to the global library only (#4102): a
    per-library copy meant every library grew its own "Default Workflows"
    container, so the same presets appeared N times across the sidebar.
    Libraries opened before this rule was introduced already hold seeded
    copies, so opening one heals it here.

    Only rows the seeder itself created are touched — ``is_system`` /
    ``is_template`` workflows whose name matches a shipped preset. A
    user-authored or renamed workflow is never removed, so a library's own
    custom workflows are untouched.

    Returns the number of workflows removed.
    """
    from fichero.models import Workflow

    presets = _load_preset_files()
    preset_names = {preset.get("name") for preset in presets if preset.get("name")}
    preset_names |= _DEPRECATED_PRESET_NAMES
    if not preset_names:
        return 0

    try:
        existing = list(db.all(Workflow))
    except Exception as exc:
        logger.warning(f"prune_default_workflows: cannot list workflows: {exc}")
        return 0

    removed = 0
    for workflow in existing:
        if workflow.name not in preset_names:
            continue
        if not (
            getattr(workflow, "is_template", False) or getattr(workflow, "is_system", False)
        ):
            continue
        try:
            # Database.delete removes the mirrored document node too.
            db.delete(workflow)
            removed += 1
        except Exception as exc:
            logger.warning(f"Could not prune default workflow '{workflow.name}': {exc}")

    # The locked container + its subfolders are created lazily whenever a
    # system workflow is saved; with the presets gone they'd linger as empty
    # system folders, so drop them in the same pass.
    db.delete_default_workflow_container_nodes()

    if removed:
        logger.info(f"Pruned {removed} default workflow(s) from non-global library")
    return removed
