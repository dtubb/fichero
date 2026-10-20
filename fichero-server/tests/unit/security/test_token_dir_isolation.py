"""FICHERO_TOKEN_DIR relocates BOTH token files (2026-08-24): a spawned test
engine's boot must never rewrite the user's real credentials — that clobber
silently 401'd every live engine ("stale_bootstrap_token") until restart."""

from pathlib import Path

from fichero_server.api import auth


def test_token_paths_relocate_under_the_override(monkeypatch, tmp_path):
    monkeypatch.setenv("FICHERO_TOKEN_DIR", str(tmp_path))
    assert auth._token_file_path() == tmp_path / ".api-key"
    sandbox = auth._sandbox_token_file_path("app.fichero.fichero")
    assert sandbox.parent == tmp_path
    assert "app.fichero.fichero" in sandbox.name


def test_default_paths_unchanged_without_the_override(monkeypatch):
    monkeypatch.delenv("FICHERO_TOKEN_DIR", raising=False)
    assert auth._token_file_path() == (
        Path.home() / "Library" / "Application Support" / "Fichero" / ".api-key"
    )
    assert "Containers" in str(auth._sandbox_token_file_path("app.fichero.fichero"))


def test_a_token_dir_engine_writes_no_token_into_uuid_containers(monkeypatch, tmp_path):
    """#5685: a scratch engine (the REALRUN script) sets FICHERO_TOKEN_DIR; startup's `sync_app_bootstrap_token` must not
    mirror its run token into the UUID-named app containers either. A fake HOME: never the real Library."""
    home = tmp_path / "home"
    support = home / "Library" / "Containers" / "123e4567-e89b-12d3-a456-426614174000" / "Data" / "Library" / "Application Support" / "Fichero"
    support.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("FICHERO_TOKEN_DIR", str(tmp_path / "tokens"))
    assert auth._uuid_sandbox_token_paths() == []
    auth.sync_app_bootstrap_token("run-token", app_id="app.fichero.fichero")
    assert not (support / ".api-key").exists()
    assert list((home / "Library").rglob(".api-key")) == []  # nothing in the fake Library at all
    assert (tmp_path / "tokens" / "sandbox-app.fichero.fichero.api-key").read_text().strip() == "run-token"

    monkeypatch.delenv("FICHERO_TOKEN_DIR")  # without the override the UUID container still gets its copy
    assert auth._uuid_sandbox_token_paths() == [support / ".api-key"]
