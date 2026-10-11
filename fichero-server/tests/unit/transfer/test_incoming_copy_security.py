"""The routes that receive a copy from another machine, and pairing out, under attack (#5657 security review).

WHY: these are the first routes where ANOTHER MACHINE writes files onto this one. A peer that could call them
anonymously, fill the disk, name a path outside its folder, point a node at any file here, or pair this engine
out from a collaborator's session would turn sharing into a hole. Driven through the real auth middleware
(the sharing probe's harness: the host app on loopback, a paired device on another Mac, people with roles)
and through the real routes.
"""

# ruff: noqa: F811 -- pytest fixtures imported from other test modules are named as test arguments
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

import pytest

from fichero_server.db.manager import db_manager
from fichero_server.models import Document
from fichero_server.models.transfer import TransferRecord
from fichero_server.transfer import remote
from tests.unit.security.test_sharing_probe_2026_10_01 import (  # noqa: F401  (fixtures)
    _bearer,
    _clear_pairing_state,
    _multiuser_on,
    _pair_as,
    harness,
)
from tests.unit.transfer._two_projects import build_box, open_source
from tests.unit.transfer.test_transfer_between_machines import (  # noqa: F401
    HEADER,
    _pair,
    _send,
    far,
)
import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[4] / "scripts"))
from _scan_files import scan_rglob  # noqa: E402

INCOMING = "/api/documents/transfer/incoming"


def _opening(transfer_id: str, objects: list[dict], *, contract: str | None = None) -> dict:
    return {"transfer_id": transfer_id, "source_machine": "peer", "source_project": "/Users/p/P.fichero",
            "contract": contract or remote.contract(),
            "manifest": {"library_id": transfer_id, "generation": 1, "objects": objects}}


def _records(data: bytes = b'{"transfer": {}, "rows": {}}') -> tuple[dict, bytes]:
    return {"rel": remote.RECORDS, "sha256": hashlib.sha256(data).hexdigest(), "size": len(data), "kind": "db"}, data


def _routes(tid: str, sha: str) -> list[tuple[str, str]]:
    return [("POST", INCOMING), ("PUT", f"{INCOMING}/{tid}/objects/{sha}"), ("POST", f"{INCOMING}/{tid}/land"),
            ("DELETE", f"{INCOMING}/{tid}"), ("GET", "/api/machines"), ("POST", "/api/machines/pair"),
            ("POST", "/api/documents/transfer/to-machine")]


# --- who may call them ------------------------------------------------------------------------------------


def test_no_route_answers_an_anonymous_caller_from_another_machine(harness):
    record, _ = _records()
    for method, path in _routes("a" * 32, record["sha256"]):
        r = harness.remote().request(method, path, json={})
        assert r.status_code in (401, 403), (method, path, r.status_code)  # 403 "loopback only": no token
    assert not (Path(harness.library) / "transfers").exists()


def test_a_paired_device_may_send_a_copy_in_but_never_pair_this_engine_out(harness):
    device = harness.pair(harness.host())
    peer = harness.remote()
    peer.headers.update(_bearer(device["device_token"]))
    record, data = _records()
    tid = "b" * 32

    opened = peer.post(INCOMING, json=_opening(tid, [record]))
    assert opened.status_code == 200, opened.text
    assert peer.put(f"{INCOMING}/{tid}/objects/{record['sha256']}", content=data,
                    headers={"Content-Type": "application/octet-stream"}).status_code == 200
    # This engine's own credentials for other machines are the owner's: a device may not use or add them.
    for method, path in (("GET", "/api/machines"), ("POST", "/api/machines/pair"),
                         ("POST", "/api/documents/transfer/to-machine")):
        body = {"address": "x.tail1.ts.net", "code": "X"} if path.endswith("pair") else {
            "items": ["x"], "machine": "m", "target_project": "/p", "pages_may_leave": True}
        r = peer.request(method, path, json=body if method == "POST" else None)
        assert r.status_code == 403, (path, r.status_code, r.text)
    # The host app (loopback, bootstrap) is the owner and may.
    assert harness.host().get("/api/machines").status_code == 200


def test_a_viewer_cannot_send_a_copy_into_a_project(harness, monkeypatch):
    _multiuser_on(harness, monkeypatch)
    viewer = _pair_as(harness, "bob", "Bob's Mac")
    peer = harness.remote()
    peer.headers.update(_bearer(viewer["device_token"]))
    record, _ = _records()
    r = peer.post(INCOMING, json=_opening("c" * 32, [record]))
    assert r.status_code == 403, r.text
    assert not (Path(harness.library) / "transfers" / "incoming" / ("c" * 32)).exists()


# --- what a peer may make this machine hold -----------------------------------------------------------------


@pytest.mark.parametrize("rel", ["../outside", "files/../../outside", "fichero.duckdb", "files/", "/etc/passwd",
                                 "files\\..\\x", "opened.json"])
def test_an_object_named_outside_the_package_layout_is_refused_before_anything_is_written(client, db, rel):
    record, _ = _records()
    bad = {"rel": rel, "sha256": "0" * 64, "size": 3, "kind": "file"}
    r = client.post(INCOMING, headers={HEADER: str(Path(db.path).parent)}, json=_opening("d" * 32, [record, bad]))
    assert r.status_code == 422, (rel, r.status_code, r.text)
    assert not (Path(db.path).parent / "transfers" / "incoming" / ("d" * 32)).exists()


def test_too_big_an_object_a_copy_or_too_little_room_is_refused_before_anything_is_written(client, db, monkeypatch):
    record, _ = _records()
    here = {HEADER: str(Path(db.path).parent)}
    huge = {"rel": "files/big.tif", "sha256": "1" * 64, "size": remote.MAX_OBJECT_BYTES + 1, "kind": "file"}
    assert client.post(INCOMING, headers=here, json=_opening("e" * 32, [record, huge])).status_code == 413
    many = [{"rel": f"files/{i}.tif", "sha256": f"{i:064x}", "size": remote.MAX_OBJECT_BYTES, "kind": "file"}
            for i in range(remote.MAX_TRANSFER_BYTES // remote.MAX_OBJECT_BYTES + 1)]
    assert client.post(INCOMING, headers=here, json=_opening("e" * 32, [record, *many])).status_code == 413
    monkeypatch.setattr(remote.shutil, "disk_usage", lambda path: type("U", (), {"free": remote.FREE_FLOOR_BYTES})())
    room = client.post(INCOMING, headers=here, json=_opening("e" * 32, [record]))
    assert room.status_code == 413 and "kept free" in room.json()["detail"]
    assert not (Path(db.path).parent / "transfers" / "incoming").exists()


def test_an_object_longer_than_declared_is_refused_and_not_kept(client, db):
    record, data = _records()
    here = {HEADER: str(Path(db.path).parent)}
    tid = "f" * 32
    assert client.post(INCOMING, headers=here, json=_opening(tid, [record])).status_code == 200
    r = client.put(f"{INCOMING}/{tid}/objects/{record['sha256']}", content=data + b"x" * 1024,
                   headers={**here, "Content-Type": "application/octet-stream"})
    assert r.status_code == 413
    assert remote.missing(db, tid) == [record["sha256"]]
    assert not (Path(db.path).parent / "transfers" / "incoming" / tid / "package").exists()


def test_an_id_or_hash_that_is_not_one_never_names_a_folder(client, db):
    here = {HEADER: str(Path(db.path).parent)}
    for path in (f"{INCOMING}/..%2F..", f"{INCOMING}/{'g' * 32}", f"{INCOMING}/{'a' * 31}"):
        assert client.delete(path, headers=here).status_code in (404, 422), path
    assert client.put(f"{INCOMING}/{'a' * 32}/objects/..%2Fx", headers=here, content=b"x").status_code in (404, 422)
    with pytest.raises(LookupError):
        remote._incoming(db, "../../etc")


def test_a_copy_nothing_arrived_for_in_a_week_is_abandoned_when_another_opens(client, db):
    here = {HEADER: str(Path(db.path).parent)}
    record, _ = _records()
    old, new = "1" * 32, "2" * 32
    assert client.post(INCOMING, headers=here, json=_opening(old, [record])).status_code == 200
    stale = Path(db.path).parent / "transfers" / "incoming" / old
    week_ago = time.time() - remote.STALE_AFTER_SECONDS - 60
    for p in [stale, *scan_rglob(stale, "*")]:
        os.utime(p, (week_ago, week_ago))

    assert client.post(INCOMING, headers=here, json=_opening(new, [record])).status_code == 200

    assert not stale.exists()
    assert (Path(db.path).parent / "transfers" / "incoming" / new).exists()


# --- what lands: the caller's, and never a path on this machine ----------------------------------------------


def test_a_landed_copy_is_the_callers_and_a_linked_original_is_never_a_path_here(client, db, tmp_path, far):
    source_package = open_source(tmp_path)
    source = db_manager.get_database(source_package)
    box = build_box(source, db, tmp_path)
    result = _send(client, source_package, db, _pair(client), [box.folder.id]).json()

    [record] = db.all(TransferRecord)
    copies = {d.name: d for d in db.all(Document) if (d.metadata or {}).get("transferred_from")}
    assert record.created_by and copies["Box 1"].metadata["transferred_from"]["who"] == record.created_by
    linked = copies["p2.png"]
    assert linked.path is None  # the source machine's path never becomes a file this engine would serve
    assert linked.metadata["linked_elsewhere"]["path"] == str(box.linked_original)
    assert str(box.linked_original) not in json.dumps({k: v for k, v in linked.metadata.items() if k != "linked_elsewhere"})
    assert result["state"] == "done"


def test_a_pairing_code_pairs_this_engine_once(client, far):
    code = client.post("/api/pair/code").json()["code"]
    first = client.post("/api/machines/pair", json={"address": "far-mac.tail1234.ts.net", "code": code})
    again = client.post("/api/machines/pair", json={"address": "far-mac.tail1234.ts.net", "code": code})
    assert first.status_code == 200 and again.status_code == 403 and "refused the pairing code" in again.json()["detail"]


def test_pairing_a_machine_needs_no_project(client, far):
    """Pairing is engine-wide: from the CLI with no project chosen it was refused for a missing library header."""
    code = client.post("/api/pair/code").json()["code"]
    r = client.post("/api/machines/pair", json={"address": "far-mac.tail1234.ts.net", "code": code},
                    headers={HEADER: ""})
    assert r.status_code == 200, r.text
