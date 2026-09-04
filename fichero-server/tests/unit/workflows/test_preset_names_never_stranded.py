"""A renamed preset must never strand its old row in a user's library.

A shipped preset's id is ``uuid5(_PRESET_ID_NAMESPACE, name)`` — the name IS
the identity. Rename "Convert to Markdown" to "AI Convert to Markdown" and the
seeder does not rename anything: it mints a NEW row for the new name and leaves
the old row sitting in every already-seeded library, forever, because nothing
ships that name any more and nothing tells the library to remove it. The user
sees two presets that do the same thing and has no way to know which is
current.

The one mechanism that prevents this is ``_DEPRECATED_PRESET_NAMES`` — names
listed there are deleted from the library on the next open. Every rename in
Fichero's history has remembered to use it. That is a convention with nothing
behind it, and conventions are forgotten by whoever is in a hurry at 2am.

So the ledger (``resources/workflow_meta/preset_name_ledger.json``) records
every name ever shipped, and this test pins two directions:

* **Nothing is stranded** — every name in the ledger is either shipped today or
  explicitly retired. A rename that forgets ``_DEPRECATED_PRESET_NAMES`` fails
  here instead of shipping quietly.
* **Nothing is unrecorded** — every shipped name is in the ledger. A new preset
  that skips the ledger fails here, so the ledger cannot silently go stale and
  start passing the first check by knowing less.

Nothing here touches a database or a model.
"""

from __future__ import annotations

import json

from fichero_server.workflows.default_workflows import (
    _DEPRECATED_PRESET_NAMES,
    _load_preset_files,
)
from fichero_server.workflows.preset_manifest import MANIFEST_PATH

# Beside the version manifest, and resolved through the PACKAGE rather than
# through this file's path — so the ledger always comes from the same tree as
# the presets `_load_preset_files` actually reads (a worktree's tests run
# against a venv whose editable install points at another checkout).
LEDGER_PATH = MANIFEST_PATH.parent / "preset_name_ledger.json"


def _ledger_names() -> set[str]:
    data = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    return set(data["names"])


def _shipped_names() -> set[str]:
    return {preset["name"] for preset in _load_preset_files() if preset.get("name")}


def _stranded(ledger: set[str], shipped: set[str], deprecated: set[str]) -> list[str]:
    """Names that once shipped and are now neither shipped nor retired."""
    return sorted(ledger - (shipped | deprecated))


def test_ledger_file_exists_and_is_populated() -> None:
    assert LEDGER_PATH.is_file(), f"preset name ledger missing at {LEDGER_PATH}"
    assert len(_ledger_names()) >= len(_shipped_names())


def test_no_shipped_name_is_missing_from_the_ledger() -> None:
    """A new preset must record its name, or the ledger goes stale unnoticed."""
    unrecorded = sorted(_shipped_names() - _ledger_names())
    assert not unrecorded, (
        "These preset names ship but are not in the ledger:\n  "
        + "\n  ".join(unrecorded)
        + f"\n\nAdd them to {LEDGER_PATH.name} under 'names'. The ledger is how "
        "a later rename gets caught; a name that never enters it can be renamed "
        "away without anything noticing."
    )


def test_every_name_ever_shipped_is_current_or_retired() -> None:
    """The guarantee: no name in the ledger has been left to strand rows."""
    stranded = _stranded(
        _ledger_names(), _shipped_names(), set(_DEPRECATED_PRESET_NAMES)
    )
    assert not stranded, (
        "These preset names once shipped but are now neither shipped nor "
        "retired:\n  "
        + "\n  ".join(stranded)
        + "\n\nEvery library seeded before the change still holds a row under "
        "each name, and nothing will ever remove it — the user sees a duplicate "
        "preset forever. Add each name to _DEPRECATED_PRESET_NAMES in "
        "workflows/default_workflows.py (with a comment saying what replaced "
        "it). Do NOT fix this by deleting the name from the ledger."
    )


# --- proof the guard fires -------------------------------------------------
# A guardrail nobody has watched fail is a guardrail nobody knows works. These
# run the same predicate over a synthetic rename, so the check is pinned even
# while the real presets are (correctly) clean.


def test_guard_catches_a_rename_that_forgot_to_retire_the_old_name() -> None:
    ledger = {"Transcribe", "Convert to Markdown"}
    shipped = {"Transcribe", "AI Convert to Markdown"}
    assert _stranded(ledger, shipped, deprecated=set()) == ["Convert to Markdown"]


def test_guard_is_satisfied_once_the_old_name_is_retired() -> None:
    ledger = {"Transcribe", "Convert to Markdown"}
    shipped = {"Transcribe", "AI Convert to Markdown"}
    assert _stranded(ledger, shipped, deprecated={"Convert to Markdown"}) == []
