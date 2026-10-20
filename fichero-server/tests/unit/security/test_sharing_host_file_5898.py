"""`sharing.synced-project-names-its-host` (#5898): sharing a library writes the non-secret `sharing-host.json` into its root."""
from __future__ import annotations

import json

import pytest

from fichero_server import sharing_host_file as shf


@pytest.fixture(autouse=True)
def _public_url(monkeypatch):
    monkeypatch.setenv("FICHERO_PUBLIC_BASE_URL", "https://mbp.local:8765")


def test_the_file_has_exactly_three_keys_and_no_secret(tmp_path):
    assert shf.write(tmp_path, "Daniel") is True
    data = json.loads((tmp_path / shf.FILE_NAME).read_text())
    assert set(data) == {"hostURL", "hostName", "person"}
    assert data["hostURL"] == "https://mbp.local:8765" and data["person"] == "Daniel"
    text = (tmp_path / shf.FILE_NAME).read_text()
    assert "fichero://" not in text and "token" not in text.lower() and "pin" not in data


def test_the_url_is_an_https_origin_only(tmp_path, monkeypatch):
    monkeypatch.setenv("FICHERO_PUBLIC_BASE_URL", "https://user:secret@mbp.local:8765/api?code=ABCD-EFGH#x")
    shf.write(tmp_path, "Daniel")
    assert json.loads((tmp_path / shf.FILE_NAME).read_text())["hostURL"] == "https://mbp.local:8765"


def test_rewriting_with_nothing_changed_leaves_the_file_alone(tmp_path):
    assert shf.write(tmp_path, "Daniel") is True
    before = (tmp_path / shf.FILE_NAME).stat().st_mtime_ns
    assert shf.write(tmp_path, "Daniel") is False
    assert (tmp_path / shf.FILE_NAME).stat().st_mtime_ns == before
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.parametrize("url", ["", "http://mbp.local:8765", "ftp://x"])
def test_no_https_address_writes_nothing(tmp_path, monkeypatch, url):
    monkeypatch.setenv("FICHERO_PUBLIC_BASE_URL", url)
    assert shf.write(tmp_path, "Daniel") is False
    assert not (tmp_path / shf.FILE_NAME).exists()


def test_an_unwritable_root_logs_and_does_not_raise(tmp_path, caplog):
    assert shf.write(tmp_path / "no" / "such" / "dir", "Daniel") is False
    assert "could not write" in caplog.text


def test_sharing_a_library_writes_it(tmp_path, monkeypatch):
    """The route's helper names the host in the shared project, with the sharer as the person to ask."""
    from types import SimpleNamespace

    from fichero_server.api.routes.auth import authz as route

    owner = SimpleNamespace(display_name="Daniel", username="daniel")
    monkeypatch.setattr(route, "get_app_db", lambda: SimpleNamespace(get_user_by_username=lambda name: None))
    monkeypatch.setattr(route, "ensure_owner_account", lambda app_db: owner)
    route._name_the_host_in_the_project(str(tmp_path), SimpleNamespace(actor="system"))
    assert json.loads((tmp_path / shf.FILE_NAME).read_text())["person"] == "Daniel"
