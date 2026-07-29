"""Engine migrates the legacy app.fichero.fichero/ tree into Fichero/ (#1526).

The SwiftUI app historically wrote the global library under its bundle id
(~/Library/Application Support/app.fichero.fichero/global.fichero). The engine's
canonical dir is ~/Library/Application Support/Fichero/. They must converge.
"""

from __future__ import annotations

from pathlib import Path

from fichero_server.db.paths import server_state_dir, migrate_legacy_server_state


def test_app_fichero_bundle_dir_migrates_into_canonical(tmp_path: Path) -> None:
    home = tmp_path
    app_support = home / "Library" / "Application Support"
    legacy = app_support / "app.fichero.fichero" / "global.fichero"
    legacy.mkdir(parents=True)
    (legacy / "fichero.duckdb").write_text("x")

    moved = migrate_legacy_server_state(home=home)

    canonical = server_state_dir(home) / "global.fichero" / "fichero.duckdb"
    assert moved >= 1
    assert canonical.exists(), "global.fichero should now live under Fichero/"


def test_canonical_dir_is_application_support_fichero(tmp_path: Path) -> None:
    d = server_state_dir(home=tmp_path)
    assert d.parts[-2:] == ("Application Support", "Fichero")
