
from fichero.db.paths import engine_state_dir, migrate_legacy_engine_state


def test_engine_state_dir_uses_fichero_convention(tmp_path):
    home = tmp_path / "home"
    expected = home / "Library" / "Application Support" / "Fichero"
    assert engine_state_dir(home) == expected


def test_migrate_legacy_engine_state_moves_old_bundle_dirs(tmp_path):
    home = tmp_path / "home"
    old_bundle = home / "Library" / "Application Support" / "com.fichero.fichero"
    older_bundle = home / "Library" / "Application Support" / "ca.tubb.fichero" / "global.fichero"
    old_bundle.mkdir(parents=True, exist_ok=True)
    older_bundle.mkdir(parents=True, exist_ok=True)
    (old_bundle / "app.duckdb").write_text("appdb")
    (older_bundle / "legacy.txt").write_text("legacy")

    moved = migrate_legacy_engine_state(home)

    target = home / "Library" / "Application Support" / "Fichero"
    assert moved == 2
    assert (target / "app.duckdb").exists()
    assert (target / "legacy.txt").exists()

