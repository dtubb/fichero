"""Engine migrates the legacy app.fichero.fichero/ tree into Fichero/ (#1526).

The SwiftUI app historically wrote the global library under its bundle id
(~/Library/Application Support/app.fichero.fichero/global.fichero). The engine's
canonical dir is ~/Library/Application Support/Fichero/. They must converge.
"""

from __future__ import annotations

from pathlib import Path

from fichero.paths import engine_state_dir, migrate_legacy_engine_state


def test_app_fichero_bundle_dir_migrates_into_canonical(tmp_path: Path) -> None:
    home = tmp_path
    app_support = home / "Library" / "Application Support"
    legacy = app_support / "app.fichero.fichero" / "global.fichero"
    legacy.mkdir(parents=True)
    (legacy / "fichero.duckdb").write_text("x")

    moved = migrate_legacy_engine_state(home=home)

    canonical = engine_state_dir(home) / "global.fichero" / "fichero.duckdb"
    assert moved >= 1
    assert canonical.exists(), "global.fichero should now live under Fichero/"


def test_ca_tubb_bundle_dir_migrates_into_canonical(tmp_path: Path) -> None:
    home = tmp_path
    app_support = home / "Library" / "Application Support"
    legacy_library = app_support / "ca.tubb.fichero" / "Library.fichero"
    legacy_library.mkdir(parents=True)
    (legacy_library / "fichero.duckdb").write_text("legacy")
    (app_support / "ca.tubb.fichero" / ".api-key").write_text("token")

    moved = migrate_legacy_engine_state(home=home)

    canonical = engine_state_dir(home)
    assert moved == 2
    assert (canonical / "Library.fichero" / "fichero.duckdb").read_text() == "legacy"
    assert (canonical / ".api-key").read_text() == "token"


def test_legacy_bundle_migration_does_not_overwrite_canonical_files(
    tmp_path: Path,
) -> None:
    home = tmp_path
    app_support = home / "Library" / "Application Support"
    legacy_library = app_support / "ca.tubb.fichero" / "Library.fichero"
    canonical_library = engine_state_dir(home) / "Library.fichero"
    legacy_library.mkdir(parents=True)
    canonical_library.mkdir(parents=True)
    (legacy_library / "fichero.duckdb").write_text("legacy")
    (canonical_library / "fichero.duckdb").write_text("canonical")

    moved = migrate_legacy_engine_state(home=home)

    assert moved == 0
    assert (canonical_library / "fichero.duckdb").read_text() == "canonical"
    assert (legacy_library / "fichero.duckdb").read_text() == "legacy"


def test_canonical_dir_is_application_support_fichero(tmp_path: Path) -> None:
    d = engine_state_dir(home=tmp_path)
    assert d.parts[-2:] == ("Application Support", "Fichero")
