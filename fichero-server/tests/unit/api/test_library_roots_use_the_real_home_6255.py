"""#6255: the sandboxed engine's ``~`` (``Path.home()``) is the app's container, so ``~/Documents`` in the allowed
roots was the container's Documents and a real ``/Users/<me>/Documents/x.fichero`` was refused (403
failed_check=roots). The roots are taken from the person's real home (the password database) as well."""
from __future__ import annotations

from pathlib import Path

import pytest

from fichero_server.security import path_security


@pytest.fixture
def sandboxed(tmp_path, monkeypatch):
    me = tmp_path / "Users" / "me"
    container = me / "Library" / "Containers" / "app.fichero.fichero" / "Data"
    (me / "Documents").mkdir(parents=True)
    container.mkdir(parents=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: container))
    monkeypatch.setattr(path_security, "_real_home", lambda: me)
    return me


def test_the_real_documents_is_an_allowed_root(sandboxed):
    roots = path_security.ingest_allowed_roots()
    assert sandboxed / "Documents" in roots
    assert sandboxed / "Library" / "Mobile Documents" / "com~apple~CloudDocs" in roots


def test_the_real_home_itself_is_never_a_grantable_folder(sandboxed):
    with pytest.raises(path_security.OwnerFolderGrantRefused):
        path_security.owner_folder_grant_key(sandboxed)
    with pytest.raises(path_security.OwnerFolderGrantRefused):
        path_security.owner_folder_grant_key(sandboxed / "Library")
