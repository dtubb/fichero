"""One setting root for every engine-owned file, and a guard that keeps tests off the real one (#5530).

WHY: the test conftest pointed FICHERO_BASE_PATH at a temp dir, yet a fixture opened the
maintainer's REAL ``global.fichero`` (a module reload had swapped in real-home settings), and the
model stores, training and remote-read job dirs, the Remote Access TLS dir and the price cache all
hung off ``Path.home()`` regardless of the base. These pin: every one of them follows the base when
it is set; none of them moves when it is not (the shipped app and the dev engine never set it);
and the session guard fails a test that reaches a real state dir, judged against a FAKE home here.
"""

from __future__ import annotations

import os
from pathlib import Path

import duckdb
import pytest

from tests import _real_state_guard as guard

_ENV = (
    "FICHERO_BASE_PATH",
    "FICHERO_MODEL_STORE_ROOT",
    "FICHERO_MLX_RUNTIME_DIR",
    "FICHERO_KRAKEN_DATA_DIR",
)


def _engine_owned_paths() -> dict[str, Path]:
    """Every engine-owned path, resolved NOW from the env (no import-time constants)."""
    from fichero_server.db.paths import model_store_root, server_state_dir
    from fichero_server.db.storage import StorageSettings
    from fichero_server.llm import kraken_runtime, mlx_model_store, mlx_runtime, model_types, whisper_runtime
    from fichero_server.remote_read import job as remote_read_job
    from fichero_server.training import job as training_job

    settings = StorageSettings()
    return {
        "state": server_state_dir(),
        "app_db": settings.app_db_path,
        "global_library": settings.global_library_path,
        "thumbnails": settings.thumb_dir,
        "snapshots": settings.snapshots_dir,
        "models": model_store_root() / "models",
        "whisper": whisper_runtime.whisper_store_dir(),
        "mlx_models": mlx_model_store.mlx_model_store_dir(),
        "mlx_runtime": mlx_runtime.mlx_runtime_dir(),
        "kraken_models": kraken_runtime._kraken_data_dir(),
        "training_job": training_job._work_dir("j1"),
        "remote_read_job": remote_read_job._work_dir("j1"),
        "model_prices": model_types._cached_registry_path(),
    }


@pytest.fixture
def clean_env(monkeypatch):
    for name in _ENV:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


class TestOneSettingRoot:
    def test_every_engine_owned_path_resolves_under_the_base_when_it_is_set(self, clean_env, tmp_path):
        base = tmp_path / "base"
        clean_env.setenv("FICHERO_BASE_PATH", str(base))
        for name, path in _engine_owned_paths().items():
            assert path == base or base in path.parents, f"{name} escaped the base: {path}"

    def test_the_global_library_is_under_the_session_base_not_the_real_home(self):
        # The exact fixture shape that opened the real registry (#5530).
        from fichero_server.db.storage import settings

        base = Path(os.environ["FICHERO_BASE_PATH"])
        assert settings.global_library_path == base / "global.fichero"
        assert guard.real_state_root(settings.global_library_path) is None

    def test_without_the_env_every_path_is_where_the_app_has_always_kept_it(self, clean_env):
        # Pure path arithmetic -- nothing is opened -- against the literal layout the shipped app
        # and the dev engine have always used.
        root = Path.home() / "Library" / "Application Support" / "Fichero"
        assert _engine_owned_paths() == {
            "state": root,
            "app_db": root / "app.duckdb",
            "global_library": root / "global.fichero",
            "thumbnails": root / "thumbnails",
            "snapshots": root / "snapshots",
            "models": root / "models",
            "whisper": root / "models" / "whisper",
            "mlx_models": root / "models" / "mlx",
            "mlx_runtime": root / "mlx-runtime",
            "kraken_models": root / "kraken-models",
            "training_job": root / "training" / "j1",
            "remote_read_job": root / "remote-read" / "j1",
            "model_prices": root / "model_prices.json",
        }

    def test_an_explicit_home_always_means_the_default_layout(self, clean_env, tmp_path):
        # `migrate_legacy_server_state(home)` and the runtimes' `home=` callers name a HOME, not a
        # base; the env must not reinterpret them.
        from fichero_server.db.paths import model_store_root, server_state_dir

        clean_env.setenv("FICHERO_BASE_PATH", str(tmp_path / "base"))
        clean_env.setenv("FICHERO_MODEL_STORE_ROOT", str(tmp_path / "models-root"))
        home = tmp_path / "home"
        assert server_state_dir(home) == home / "Library" / "Application Support" / "Fichero"
        assert model_store_root(home) == home / "Library" / "Application Support" / "Fichero"

    def test_the_model_store_opt_in_moves_only_the_model_stores(self, clean_env, tmp_path):
        base, store = tmp_path / "base", tmp_path / "store"
        clean_env.setenv("FICHERO_BASE_PATH", str(base))
        clean_env.setenv("FICHERO_MODEL_STORE_ROOT", str(store))
        paths = _engine_owned_paths()
        for name in ("models", "whisper", "mlx_models", "mlx_runtime", "kraken_models"):
            assert store in paths[name].parents, name
        for name in ("app_db", "global_library", "training_job", "remote_read_job", "model_prices"):
            assert base in paths[name].parents, name

    def test_the_session_model_stores_are_temp(self):
        # #5528: the spaCy row read the machine's real store. The import-time constant is the one
        # the catalog uses, so check it, not a fresh resolution.
        from fichero_server.llm.local_models import MODELS_BASE

        assert Path(os.environ["FICHERO_BASE_PATH"]) / "models" == MODELS_BASE
        assert "FICHERO_MODEL_STORE_ROOT" not in os.environ


@pytest.fixture
def fake_real_home(monkeypatch, tmp_path):
    """Judge against a fake home's state dir, so nothing real is ever touched by these tests."""
    root = tmp_path / "fakehome" / "Library" / "Application Support" / "Fichero"
    root.mkdir(parents=True)
    (root / "config.json").write_text("{}")  # made before the guard looks at this root
    monkeypatch.setattr(guard, "ROOTS", (os.path.realpath(root),))
    yield root
    guard.drain()  # the refusals below are this test's point, not a failure of it


class TestTheGuard:
    def test_it_is_armed_for_the_whole_session_against_the_real_home(self):
        import pwd

        assert getattr(duckdb.connect, "_fichero_real_state_guard", False)
        real = os.path.realpath(pwd.getpwuid(os.getuid()).pw_dir)
        assert os.path.join(real, "Library", "Application Support", "Fichero") in guard.ROOTS
        assert os.path.join(real, "Library", "Application Support", "com.fichero.fichero") in guard.ROOTS

    def test_opening_a_duckdb_file_there_fails_naming_the_test(self, fake_real_home):
        target = fake_real_home / "global.fichero" / "fichero.duckdb"
        with pytest.raises(AssertionError, match="test_opening_a_duckdb_file_there_fails_naming_the_test"):
            duckdb.connect(str(target))
        with pytest.raises(AssertionError):
            duckdb.connect(str(target), read_only=True)  # a read-only open still takes the lock
        assert not target.exists()

    def test_writing_there_fails_and_is_recorded_even_when_swallowed(self, fake_real_home):
        try:
            (fake_real_home / "registry.json").write_text("{}")
        except AssertionError:
            pass  # the shape of a caller that logs and carries on
        recorded = guard.drain()
        assert len(recorded) == 1 and "registry.json" in recorded[0]
        assert not (fake_real_home / "registry.json").exists()
        with pytest.raises(AssertionError):
            (fake_real_home / "new-dir").mkdir()
        with pytest.raises(AssertionError):
            os.symlink("/tmp", fake_real_home / "link")

    def test_a_link_into_it_does_not_launder_a_write(self, fake_real_home, tmp_path):
        link = tmp_path / "models"
        link.symlink_to(fake_real_home, target_is_directory=True)
        with pytest.raises(AssertionError):
            (link / "weights.bin").write_bytes(b"x")

    def test_reads_there_and_writes_elsewhere_pass(self, fake_real_home, tmp_path):
        assert (fake_real_home / "config.json").read_text() == "{}"  # reads are not judged
        fake_real_home.mkdir(parents=True, exist_ok=True)  # exists already: writes nothing
        (tmp_path / "ok.json").write_text("{}")
        duckdb.connect(str(tmp_path / "ok.duckdb")).close()
        duckdb.connect(":memory:").close()
        assert guard.drain() == []

    def test_the_app_container_is_guarded_and_a_socket_cannot_be_bound_or_unlinked_there(self, monkeypatch):
        # 2026-10-06: the running app's engine socket (~/Library/Containers/app.fichero.fichero/
        # Data/tmp/fichero.sock) vanished under a live engine. The container is a guarded root,
        # and a bind or unlink there is refused. A short fake root: AF_UNIX paths cap at 104 bytes.
        import shutil
        import socket
        import tempfile

        real_container = os.path.join(guard.REAL_HOME, "Library", "Containers", "app.fichero.fichero")
        assert real_container in guard.ROOTS
        root = tempfile.mkdtemp(prefix="fsg-", dir="/tmp")
        try:
            sock_path = os.path.join(root, "f.sock")
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as existing:
                existing.bind(sock_path)  # made before the guard looks at this root
            monkeypatch.setattr(guard, "ROOTS", (os.path.realpath(root),))
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                with pytest.raises(AssertionError, match="binds a socket at"):
                    s.bind(os.path.join(root, "g.sock"))
            with pytest.raises(AssertionError, match="removes"):
                Path(sock_path).unlink()
            assert os.path.exists(sock_path)
        finally:
            monkeypatch.undo()
            guard.drain()
            shutil.rmtree(root, ignore_errors=True)
