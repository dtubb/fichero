"""`sharing.synced-project-names-its-host` (#5898, ## 542/544): sharing a library writes the non-secret `sharing-host.json` into its
root, but only the engine that OWNS the project (the first to share, by engine id) ever writes or rewrites it."""
from __future__ import annotations

import json

import pytest

from fichero_server import sharing_host_file as shf
from fichero_server.security import synced_host

MINE, OTHER = "engine-mine-0000000000", "engine-other-000000000"


@pytest.fixture(autouse=True)
def _engine(monkeypatch):
    monkeypatch.setenv("FICHERO_PUBLIC_BASE_URL", "https://mbp.local:8765")
    monkeypatch.setattr(synced_host, "this_engine_id", lambda: MINE)
    monkeypatch.setattr(synced_host, "is_this_engine", lambda host_engine_id: bool(host_engine_id) and host_engine_id == MINE)
    monkeypatch.setattr(shf, "_host_name", lambda: "Daniel's MacBook Pro")


def _file(root):
    return json.loads((root / shf.FILE_NAME).read_text())


def test_the_file_has_exactly_four_keys_and_no_secret(tmp_path):
    assert shf.write(tmp_path, "Daniel") is True
    data = _file(tmp_path)
    assert set(data) == {"hostURL", "hostName", "person", "hostEngineId"}
    assert data == {"hostURL": "https://mbp.local:8765", "hostName": "Daniel's MacBook Pro", "person": "Daniel", "hostEngineId": MINE}
    text = (tmp_path / shf.FILE_NAME).read_text()
    assert "fichero://" not in text and "token" not in text.lower()
    assert synced_host.read_synced_host(tmp_path) is not None, "the guest's own validator accepts what the host writes"


def test_the_url_is_an_https_origin_only(tmp_path, monkeypatch):
    monkeypatch.setenv("FICHERO_PUBLIC_BASE_URL", "https://user:secret@mbp.local:8765/api?code=ABCD-EFGH#x")
    shf.write(tmp_path, "Daniel")
    assert _file(tmp_path)["hostURL"] == "https://mbp.local:8765"


def test_rewriting_with_nothing_changed_leaves_the_file_alone(tmp_path):
    assert shf.write(tmp_path, "Daniel") is True
    before = (tmp_path / shf.FILE_NAME).stat().st_mtime_ns
    assert shf.write(tmp_path, "Daniel") is False
    assert (tmp_path / shf.FILE_NAME).stat().st_mtime_ns == before
    assert not list(tmp_path.glob("*.tmp")) and not list(tmp_path.glob(".sharing-host.*"))


def test_the_owning_engine_rewrites_its_own_file_when_a_field_changes(tmp_path):
    shf.write(tmp_path, "Daniel")
    assert shf.write(tmp_path, "Maya") is True
    assert _file(tmp_path)["person"] == "Maya" and _file(tmp_path)["hostEngineId"] == MINE


def test_a_guests_engine_never_overwrites_another_engines_file(tmp_path, monkeypatch):
    """The synced copy names the HOST; a share made on the guest's own engine (Sharing on there) must not replace it."""
    shf.write(tmp_path, "Daniel")
    host_text = (tmp_path / shf.FILE_NAME).read_text()
    monkeypatch.setattr(synced_host, "this_engine_id", lambda: OTHER)
    monkeypatch.setattr(synced_host, "is_this_engine", lambda host_engine_id: host_engine_id == OTHER)
    monkeypatch.setenv("FICHERO_PUBLIC_BASE_URL", "https://guest.local:8765")
    assert shf.write(tmp_path, "Guest") is False
    assert (tmp_path / shf.FILE_NAME).read_text() == host_text


@pytest.mark.parametrize("content", ["{not json", json.dumps({"hostURL": "https://x:1", "hostName": "n", "person": "p"}),
                                     json.dumps({"hostURL": "https://x:1", "hostName": "n", "person": "p", "hostEngineId": "e", "extra": 1})])
def test_a_file_this_engine_cannot_read_as_its_own_is_left_alone(tmp_path, content):
    (tmp_path / shf.FILE_NAME).write_text(content)
    assert shf.write(tmp_path, "Daniel") is False
    assert (tmp_path / shf.FILE_NAME).read_text() == content


def test_the_first_engine_to_share_records_itself(tmp_path):
    assert not (tmp_path / shf.FILE_NAME).exists()
    assert shf.write(tmp_path, "Daniel") is True
    assert _file(tmp_path)["hostEngineId"] == MINE


@pytest.mark.parametrize("url", ["", "http://mbp.local:8765", "ftp://x"])
def test_no_https_address_writes_nothing(tmp_path, monkeypatch, url):
    monkeypatch.setenv("FICHERO_PUBLIC_BASE_URL", url)
    assert shf.write(tmp_path, "Daniel") is False
    assert not (tmp_path / shf.FILE_NAME).exists()


def test_the_temp_file_has_a_unique_name_and_none_is_left(tmp_path, monkeypatch):
    seen = []
    real = shf.os.replace
    monkeypatch.setattr(shf.os, "replace", lambda a, b: (seen.append(a), real(a, b))[1])
    shf.write(tmp_path, "Daniel")
    shf.write(tmp_path, "Maya")
    assert len(seen) == 2 and seen[0] != seen[1] and all(shf.FILE_NAME + ".tmp" not in s for s in seen)
    assert [p.name for p in tmp_path.iterdir()] == [shf.FILE_NAME]


def test_an_unwritable_root_logs_and_does_not_raise(tmp_path, caplog):
    assert shf.write(tmp_path / "no" / "such" / "dir", "Daniel") is False
    assert "could not write" in caplog.text


def test_the_host_name_is_the_name_the_person_sees(monkeypatch):
    monkeypatch.undo()  # the real _host_name, with scutil faked
    monkeypatch.setattr(shf.subprocess, "run", lambda *a, **k: type("R", (), {"stdout": "Daniel's MacBook Pro\n"})())
    assert shf._host_name() == "Daniel's MacBook Pro"
    monkeypatch.setattr(shf.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError()))
    assert shf._host_name()  # falls back to the host name slug


def test_sharing_a_library_writes_it(tmp_path, monkeypatch):
    """The route's helper names the host in the shared project, with the sharer as the person to ask."""
    from types import SimpleNamespace

    from fichero_server.api.routes.auth import authz as route

    owner = SimpleNamespace(display_name="Daniel", username="daniel")
    monkeypatch.setattr(route, "get_app_db", lambda: SimpleNamespace(get_user_by_username=lambda name: None))
    monkeypatch.setattr(route, "ensure_owner_account", lambda app_db: owner)
    route._name_the_host_in_the_project(str(tmp_path), SimpleNamespace(actor="system"))
    assert _file(tmp_path)["person"] == "Daniel"


def test_names_are_clipped_to_what_the_guests_reader_accepts(tmp_path, monkeypatch):
    """A long or odd ComputerName (or person) must not make the guest's validator reject the whole file."""
    monkeypatch.undo()  # the real _host_name (the autouse fake is dropped), with scutil faked below
    monkeypatch.setenv("FICHERO_PUBLIC_BASE_URL", "https://mbp.local:8765")
    monkeypatch.setattr(synced_host, "this_engine_id", lambda: MINE)
    monkeypatch.setattr(synced_host, "is_this_engine", lambda host_engine_id: host_engine_id == MINE)
    monkeypatch.setattr(shf.subprocess, "run", lambda *a, **k: type("R", (), {"stdout": ("Daniel\n's https://evil.example " + "x" * 400) + "\n"})())
    assert shf.write(tmp_path, "Maya\x00 " + "y" * 300) is True
    data = _file(tmp_path)
    assert 1 <= len(data["hostName"]) <= 200 and "://" not in data["hostName"] and "\n" not in data["hostName"]
    assert 1 <= len(data["person"]) <= 200
    assert synced_host.read_synced_host(tmp_path) is not None, "the guest's own validator accepts the clipped file"


def test_clip_leaves_a_plain_name_alone_and_empties_a_link():
    assert shf._clip("Daniel's MacBook Pro") == "Daniel's MacBook Pro"
    assert shf._clip("https://") == "https", "nothing link-like survives"
    assert shf._clip("   ") == ""
