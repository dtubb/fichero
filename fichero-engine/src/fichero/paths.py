"""Canonical engine storage paths and one-time legacy migration."""

from __future__ import annotations

import shutil
from pathlib import Path

_LEGACY_APP_SUPPORT_DIRS = (
    ("com.fichero.fichero",),
    ("ca.tubb.fichero", "global.fichero"),
    # The SwiftUI app historically wrote the global library under its bundle id
    # (~/Library/Application Support/app.fichero.fichero/) — migrate it into the
    # canonical Fichero/ dir so all data lives in one place (#1526).
    ("app.fichero.fichero",),
)


def engine_state_dir(home: Path | None = None) -> Path:
    base_home = home or Path.home()
    return base_home / "Library" / "Application Support" / "Fichero"


def migrate_legacy_engine_state(home: Path | None = None) -> int:
    """Move legacy engine state trees into the canonical Fichero directory."""
    base_home = home or Path.home()
    app_support = base_home / "Library" / "Application Support"
    target = engine_state_dir(base_home)
    target.mkdir(parents=True, exist_ok=True)

    migrated_entries = 0
    for legacy_parts in _LEGACY_APP_SUPPORT_DIRS:
        legacy_root = app_support.joinpath(*legacy_parts)
        if not legacy_root.exists() or legacy_root == target:
            continue
        for entry in legacy_root.iterdir():
            dest = target / entry.name
            if dest.exists():
                continue
            shutil.move(str(entry), str(dest))
            migrated_entries += 1
    return migrated_entries

