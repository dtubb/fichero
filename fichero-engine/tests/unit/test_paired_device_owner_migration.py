"""Regression coverage for consolidating the former pairing owner identity."""

from __future__ import annotations

from fichero.security import accounts
from fichero.db.app import AppDatabase


def _owner(db: AppDatabase, username: str):
    return db.create_user(
        username=username,
        display_name=username,
        password_hash=accounts.hash_password("test-password"),
        is_owner=True,
    )


def test_reopen_consolidates_paired_device_owner_references(tmp_path):
    path = tmp_path / "app.duckdb"
    db = AppDatabase(path)
    canonical = _owner(db, "owner")
    legacy = _owner(db, "__paired_device_owner__")
    device = db.create_device(
        name="Paired iPad",
        user_id=legacy.id,
        token_hash=accounts.hash_token("device-token"),
    )
    db.set_library_role(user_id=legacy.id, library_path="/library", role="editor")
    db.close()

    reopened = AppDatabase(path)
    migrated_legacy = reopened.get_user(legacy.id)
    migrated_device = next(
        item for item in reopened.list_devices() if item.id == device.id
    )
    migrated_role = reopened.get_library_role(canonical.id, "/library")

    assert migrated_legacy is not None and migrated_legacy.active is False
    assert migrated_device.user_id == canonical.id
    assert migrated_role is not None and migrated_role.role == "editor"

    reopened.close()
    again = AppDatabase(path)
    assert again.get_user(legacy.id).active is False
    assert again.get_library_role(canonical.id, "/library").role == "editor"
    again.close()
