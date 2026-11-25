
from fichero_server.db.paths import server_state_dir, migrate_legacy_server_state


def test_server_state_dir_uses_fichero_convention(tmp_path):
    home = tmp_path / "home"
    expected = home / "Library" / "Application Support" / "Fichero"
    assert server_state_dir(home) == expected


def test_migrate_legacy_server_state_moves_old_bundle_dirs(tmp_path):
    home = tmp_path / "home"
    old_bundle = home / "Library" / "Application Support" / "com.fichero.fichero"
    older_bundle = home / "Library" / "Application Support" / "ca.tubb.fichero" / "global.fichero"
    old_bundle.mkdir(parents=True, exist_ok=True)
    older_bundle.mkdir(parents=True, exist_ok=True)
    (old_bundle / "app.duckdb").write_text("appdb")
    (older_bundle / "legacy.txt").write_text("legacy")

    moved = migrate_legacy_server_state(home)

    target = home / "Library" / "Application Support" / "Fichero"
    assert moved == 2
    assert (target / "app.duckdb").exists()
    assert (target / "legacy.txt").exists()


def test_an_engine_on_its_own_base_path_leaves_the_homes_application_support_alone(tmp_path, monkeypatch):
    """GitHub run 45676804358: every engine start in the suite made ~/Library/Application Support/Fichero on a runner
    that had none. With $FICHERO_BASE_PATH set and no home named, nothing under the home is made or moved."""
    from pathlib import Path

    home = tmp_path / "home"
    legacy = home / "Library" / "Application Support" / "com.fichero.fichero"
    legacy.mkdir(parents=True)
    (legacy / "app.duckdb").write_text("appdb")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setenv("FICHERO_BASE_PATH", str(tmp_path / "base"))

    assert migrate_legacy_server_state() == 0
    assert not (home / "Library" / "Application Support" / "Fichero").exists()
    assert (legacy / "app.duckdb").read_text() == "appdb", "the legacy tree stays where it is"

