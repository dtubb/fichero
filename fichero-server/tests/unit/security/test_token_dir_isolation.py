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
