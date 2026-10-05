"""What the engine's owner allowed, kept in the global registry across restarts (#5464, #5484).

The persistence half of the owner allowances in ``api/routes/library/registry.py``: the packages
the owner opened (``owner_opened_packages``) and the folders the owner picked in the app's panel
(``owner_granted_folders``). Paths are stored resolved and NFC-normalised by the caller.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fichero_server.core.timeutil import utc_now

if TYPE_CHECKING:
    from fichero_server.db import Database


def add_opened_package(db: Database, path: str) -> None:
    db.execute(
        "INSERT INTO owner_opened_packages (path, opened_at) VALUES (?, ?) ON CONFLICT (path) DO NOTHING",
        [path, utc_now()],
    )


def opened_packages(db: Database) -> list[str]:
    return [row[0] for row in db.execute_fetchall("SELECT path FROM owner_opened_packages")]


def remove_opened_package(db: Database, path: str) -> None:
    db.execute("DELETE FROM owner_opened_packages WHERE path = ?", [path])


def add_granted_folder(db: Database, path: str) -> None:
    db.execute(
        "INSERT INTO owner_granted_folders (path, granted_at) VALUES (?, ?) ON CONFLICT (path) DO NOTHING",
        [path, utc_now()],
    )


def granted_folders(db: Database) -> list[str]:
    return [row[0] for row in db.execute_fetchall("SELECT path FROM owner_granted_folders")]
