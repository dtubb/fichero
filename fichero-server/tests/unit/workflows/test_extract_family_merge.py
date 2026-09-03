"""The Extract / Extract Data merge (Daniel, 2026-09-03).

One /Extract family: text-structure extraction (Diary Entries), table/data
extraction (Extract Table, Accounts → Spreadsheet, Extract Geo), and the
paleography derivations that shipped under /Extract Data (Regesto,
Modernización, Translate to English (Historical)) until a dedicated home is
ruled on. /Extract Data is retired from the served folder taxonomy; existing
libraries heal through the preset_version bumps that moved each preset.
"""

from __future__ import annotations

import json
from pathlib import Path

from fichero_server.workflows.default_workflows import _load_preset_files

_RESOURCES = (
    Path(__file__).resolve().parents[3] / "src" / "fichero_server" / "resources"
)

_MERGED_INTO_EXTRACT = {
    "Diary Entries",
    "Extract Table",
    "Extract Geo",
    "Accounts → Spreadsheet (CSV)",
    "Regesto (Archival Abstract)",
    "Modernización (Spanish)",
    "Translate to English (Historical)",
}


def test_extract_family_members_all_live_in_extract():
    presets = {p["name"]: p for p in _load_preset_files()}
    for name in _MERGED_INTO_EXTRACT:
        assert name in presets, f"missing preset: {name}"
        assert presets[name].get("folder_path") == "/Extract", (
            f"{name}: expected /Extract, got {presets[name].get('folder_path')!r}"
        )


def test_no_preset_ships_in_extract_data():
    for preset in _load_preset_files():
        assert preset.get("folder_path") != "/Extract Data", (
            f"{preset['name']} still ships in the retired /Extract Data folder"
        )


def test_extract_data_folder_retired_from_taxonomy():
    folders = json.loads((_RESOURCES / "workflow_folders.json").read_text())
    paths = [f["path"] for f in folders["folders"]]
    assert "/Extract" in paths
    assert "/Extract Data" not in paths
