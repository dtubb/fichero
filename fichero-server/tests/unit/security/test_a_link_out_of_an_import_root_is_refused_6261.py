"""WHY (`importer.import-roots-checked-resolved`, #6261): a symlink placed inside an allowed root (Documents) that
points elsewhere passed the ingest check, because the unresolved path was tried too. Only the resolved path counts,
against the resolved roots, so iCloud's symlinked ~/Documents still imports."""
from __future__ import annotations

from pathlib import Path

from fichero_server.security import path_security
from fichero_server.security.path_security import is_allowed_ingest_path


def _home(tmp_path, monkeypatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    monkeypatch.setenv("HOME", str(home))  # `~` expands from HOME
    # pytest's tmp dirs live under /var/folders, itself an allowed root; drop it so only the home roots decide.
    roots = path_security.ingest_allowed_roots
    monkeypatch.setattr(path_security, "ingest_allowed_roots",
                        lambda: [r for r in roots() if r not in (Path("/var/folders"), Path("/private/var/folders"))])
    return home


def test_a_symlink_in_documents_pointing_outside_is_refused(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    (home / "Documents").mkdir()
    (home / "Documents" / "passwd").symlink_to("/etc/passwd")
    assert not is_allowed_ingest_path(home / "Documents" / "passwd")


def test_icloud_documents_through_its_symlink_is_allowed(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    cloud = home / "Library" / "Mobile Documents" / "com~apple~CloudDocs" / "Documents"
    cloud.mkdir(parents=True)
    (cloud / "page.jpg").write_bytes(b"x")
    (home / "Documents").symlink_to(cloud)
    assert is_allowed_ingest_path(home / "Documents" / "page.jpg")
    assert is_allowed_ingest_path("~/Documents/page.jpg")
