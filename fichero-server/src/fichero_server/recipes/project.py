"""A project's setup answers and recipe, kept as files in the project folder (#4951).

`source/models-chains-and-projects.md`: `source.project.has-settings` (purpose, recipe, defaults)
and `source.recipe.folder-format`. The project folder holds `recipe/recipe.yaml` (the recipe, the
shareable format) and `recipe/setup.yaml` (setup's answers, so the person can come back to them).
Files, not database rows: they travel with the project, a person can read them, and the recipe is
already in the form it is shared in. A project never set up has neither file and behaves exactly
as before. Nothing here runs anything: saving is not Start (`source.project.automatic-after-first-yes`).
"""
from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from typing import Any

from fichero_server.recipes.recipe import _walk_forbidden

logger = logging.getLogger(__name__)

FOLDER = "recipe"
_FILES = {"recipe": "recipe.yaml", "answers": "setup.yaml"}


def _path(library: Path, part: str) -> Path:
    return Path(library) / FOLDER / _FILES[part]


def read_project_setup(library: Path) -> dict[str, Any]:
    """`{"answers": ..., "recipe": ...}`, each None when the project has not saved one. The answers
    are read in today's shape (`recipes/answers.py`): a project saved with one `purpose` reads as a
    list of one, a language name as its tag where it resolves; nothing is lost. What the project saved, never
    narrowed by the app's places (`recipes/places.py`): those cap at USE (`places.may_leave_to`), so no save can
    narrow a stored answer."""
    import yaml

    from fichero_server.recipes.answers import normalise

    out: dict[str, Any] = {}
    for part in _FILES:
        path = _path(library, part)
        out[part] = yaml.safe_load(path.read_text(encoding="utf-8")) if path.is_file() else None
    out["answers"] = normalise(out["answers"], strict=False)
    # Beside the answers, never in them: a save writes the answers back, and an inherited yes written there would freeze the
    # app's setting at the moment of the save and audit a yes nobody gave (`source.onboard.new-project-inherits-the-cloud-setting`).
    from fichero_server.recipes.places import inherits_cloud

    out["cloud_inherited"] = "cloud_allowed" not in (out["answers"] or {}) and inherits_cloud()
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


def holds_moves(library: Path) -> bool:
    """Set Up chose Move and Start has not been pressed (#6245): an import copies and leaves the source where it is
    until Start, so a project deleted or cancelled mid-setup never leaves the person's files displaced."""
    import yaml

    path = _path(library, "answers")
    if not path.is_file() or read_start(library) is not None:
        return False
    answers = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return str(answers.get("ingest_mode") or "").lower() == "move"


def finish_held_moves(db: Any) -> int:
    """Start's half of #6245: delete the source of every file Set Up held (`move_pending`), once Start commits.
    Returns how many were held."""
    from fichero_server.models import Document

    # ponytail: one walk of the project's documents, only when Set Up chose Move; a metadata index if Start slows.
    held = [d for d in db.query(Document) if (d.metadata or {}).get("move_pending")]
    sources = []
    for doc in held:
        doc.metadata.pop("move_pending")
        db.save(doc)
        if doc.metadata.get("source_path"):
            sources.append(Path(doc.metadata["source_path"]))

    def delete_sources() -> None:
        for source in sources:
            try:
                source.unlink(missing_ok=True)
            except OSError as exc:
                logger.warning("Start could not finish moving %s: %s", source, exc)

    db.add_after_commit_hook(delete_sources)
    return len(held)


#: The jobs proposed for the material already in the project when a layer is added later
#: (`source.onboard.add-layer`): which layers, which recipe steps, and when. Nothing runs from it;
#: the Start plan shows those steps with their estimate, and Start runs them and clears it.
PROPOSED_FILE = "proposed.yaml"


def read_proposed(library: Path) -> dict[str, Any] | None:
    import yaml

    path = Path(library) / FOLDER / PROPOSED_FILE
    return yaml.safe_load(path.read_text(encoding="utf-8")) if path.is_file() else None


def write_proposed(library: Path, proposal: dict[str, Any] | None) -> None:
    """Record (or, with None, withdraw) the jobs proposed for the material already there."""
    path = Path(library) / FOLDER / PROPOSED_FILE
    if proposal is None:
        path.unlink(missing_ok=True)
    else:
        _write_yaml(path, proposal)


def read_noise_band(library: Path) -> dict[str, Any]:
    """The project's noise band (`source.train.noise-band-per-project`, #5692): `value` (a CER difference), whether it
    was `measured` here, and its `basis` in words. Until an evaluation measures it, the ruled 0.5 CER points."""
    import yaml

    from fichero_server.training.reasons_ab import NOISE_BAND

    path = Path(library) / FOLDER / "noise-band.yaml"
    stored = yaml.safe_load(path.read_text(encoding="utf-8")) if path.is_file() else None
    if isinstance(stored, dict) and isinstance(stored.get("value"), (int, float)):
        return {"value": float(stored["value"]), "measured": True, "basis": str(stored.get("basis") or "measured")}
    return {"value": NOISE_BAND, "measured": False,
            "basis": f"{NOISE_BAND * 100:.1f} CER points, the ruled band until this project's pages measure one"}


def write_noise_band(library: Path, value: float, *, pages: int, model: str) -> None:
    """Store the band an evaluation measured: the CER spread over three held-out splits of `pages` read by `model`."""
    _write_yaml(Path(library) / FOLDER / "noise-band.yaml", {
        "value": round(float(value), 6),
        "basis": f"CER spread over 3 held-out splits of {pages} pages read by {model}"})


#: The recipe file's `defaults.record_rule`, by file and modified time: the rule is asked on every page's working pass, so
#: the file is read again only when it changes (`source.project.record-rule`).
_RECORD_RULES: dict[str, tuple[int, str]] = {}


def saved_record_rule(library: Path) -> str:
    """The saved recipe's `defaults.record_rule` as a lowercase word, "" when there is none."""
    path = _path(library, "recipe")
    try:
        stamp = path.stat().st_mtime_ns
    except OSError:
        return ""
    kept = _RECORD_RULES.get(str(path))
    if kept is not None and kept[0] == stamp:
        return kept[1]
    import yaml

    recipe = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    value = str(((recipe.get("defaults") or {}) if isinstance(recipe, dict) else {}).get("record_rule") or "").strip().lower()
    _RECORD_RULES[str(path)] = (stamp, value)
    return value
