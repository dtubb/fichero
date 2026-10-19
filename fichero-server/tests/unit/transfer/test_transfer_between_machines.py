"""A copy to another machine: packaged here, pushed, landed there all or nothing (#5657, "Between machines").

WHY: between machines a transfer is always a copy, over a network that drops. A copy that landed half a
package would leave pages without their lines on the far Mac; one that re-sent everything after a drop would
cost a person hours on a large box; one landed by different code than a copy between two projects would drift
from it. These pin, through the real routes of two engines (two projects in one test process, the far engine
reached through its own routes with its own library header, as the carrier reaches it):

- `transfer.machine.one-code-path`: what lands is what a copy on one engine plans, kind by kind;
- `transfer.machine.copy-only`: the source is unchanged but for its record;
- `transfer.machine.carriers-reused` / `drop-resumes-or-rolls-back`: a drop part-way lands nothing; sent
  again, only the missing objects travel; a failed landing rolls back and lands on retry, sending nothing;
  an abandoned copy removes what arrived;
- `transfer.machine.paired-only`: pairing by code, a version mismatch refused; the pages' yes required;
- `transfer.machine.linked-files-said`: a linked original is said to stay on the source machine.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from fichero_server.api.main import app
from fichero_server.db.manager import db_manager
from fichero_server.models import ActionAudit, Document
from fichero_server.models.knowledge import EntityMatchCandidate
from fichero_server.models.transfer import TransferRecord
from fichero_server.transfer import copy as transfer_copy
from fichero_server.transfer import machines, remote
from tests.unit.transfer._two_projects import (
    build_box,
    header_decides,
    open_source,
    table_counts,
)

HEADER = "X-Fichero-Library-Path"


class FarEngine:
    """The far engine as the carrier reaches it: its own routes, through the test client. `drop_after` puts
    break the connection after that many objects arrived, as a network that went away does."""

    def __init__(self, client):
        self.client, self.puts, self.drop_after = client, 0, None

    def post(self, *a, **k):
        return self.client.post(*a, **k)

    def put(self, *a, **k):
        if self.drop_after is not None and self.puts >= self.drop_after:
            raise httpx.ConnectError("the far Mac went to sleep")
        self.puts += 1
        return self.client.put(*a, **k)

    def close(self):
        pass


@pytest.fixture
def far(client, monkeypatch):
    header_decides(app)
    keychain: dict[str, str] = {}
    monkeypatch.setattr(machines, "_put", lambda account, secret: keychain.__setitem__(account, secret) or True)
    monkeypatch.setattr(machines, "_get", keychain.get)
    monkeypatch.setattr(machines, "_accounts", lambda: list(keychain))
    monkeypatch.setattr(machines, "_delete", lambda account: keychain.pop(account, None) is not None)
    engine = FarEngine(client)
    monkeypatch.setattr(machines, "client", lambda url, token=None: engine)
    return engine


def _pair(client) -> str:
    code = client.post("/api/pair/code").json()["code"]
    paired = client.post("/api/machines/pair", json={"address": "far-mac.tail1234.ts.net", "code": code})
    assert paired.status_code == 200, paired.text
    assert [m["id"] for m in client.get("/api/machines").json()] == [paired.json()["id"]]
    assert paired.json()["url"] == "https://far-mac.tail1234.ts.net" and "token" not in paired.json()
    return paired.json()["id"]


def _send(client, source_package, target_db, machine, items=None, resume=None, **extra):
    body = {"items": items or ["x"], "machine": machine, "target_project": str(Path(target_db.path).parent),
            "pages_may_leave": True, **({"resume": resume} if resume else {}), **extra}
    return client.post("/api/documents/transfer/to-machine", headers={HEADER: str(source_package)}, json=body)


def _landed(db) -> list[Document]:
    return [d for d in db.all(Document) if (d.metadata or {}).get("transferred_from")]


def test_a_copy_to_another_machine_lands_what_a_copy_on_one_engine_would(client, db, tmp_path, far):
    source_package = open_source(tmp_path)
    source = db_manager.get_database(source_package)
    box = build_box(source, db, tmp_path)
    source_before = table_counts(source)
    planned = client.post("/api/documents/transfer", headers={HEADER: str(Path(db.path).parent)},
                          json={"items": [box.folder.id], "source": str(source_package), "dry_run": True}).json()
    machine = _pair(client)

    response = _send(client, source_package, db, machine, [box.folder.id])

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["state"] == "done" and result["mode"] == "copy" and result["machine"] == "far-mac"
    # One code path: every kind lands as a copy between two projects would plan it, read back.
    assert {c["kind"]: c["planned"] for c in result["counts"]} == {c["kind"]: c["planned"] for c in planned["counts"]}
    assert all(c["written"] == c["planned"] for c in result["counts"])
    # Cuts and what stayed behind are listed as on one engine.
    assert sorted((c["kind"], c["row"]) for c in result["cuts"]) == sorted((c["kind"], c["row"]) for c in planned["cuts"])
    assert [b["name"] for b in result["left_behind"]] == ["torn.png"]
    # The entity is a proposed merge there, never merged.
    proposal = db.get(EntityMatchCandidate, result["proposals"][0]["proposal"])
    assert proposal.survivor_entity_id == box.target_entity.id and proposal.state.value == "pending"
    # Provenance there: the machine and project each node came from.
    [folder_id] = result["copies"]
    came = db.get(Document, folder_id).metadata["transferred_from"]
    assert came["machine"] == machines.this_machine() and came["project_path"] == str(source_package)
    assert came["node"] == box.folder.id
    # The in-package original arrived byte for byte; the linked one is said to stay on the source machine.
    pages = {d.name: d for d in db.query(Document, parent_id=folder_id)}
    assert Path(pages["p1.png"].path).read_bytes() == Path(box.page1.path).read_bytes()
    assert pages["p2.png"].metadata["linked_elsewhere"]["path"] == str(box.linked_original)
    assert any("stays at" in said and str(box.linked_original) in said for said in result["linked_elsewhere"])
    # A copy, always: the source is unchanged but for its record, done, naming the machine, and the audit of the send.
    after = table_counts(source)
    assert after.pop("ActionAudit") == source_before.pop("ActionAudit") + 1 and after == source_before
    assert [a.action_name for a in source.all(ActionAudit)] == ["document.transfer_to_machine"]
    [mirror] = source.all(TransferRecord)
    assert mirror.state.value == "done" and mirror.role.value == "source" and mirror.target_project.startswith("far-mac:")
    [record] = db.all(TransferRecord)
    assert record.role.value == "target" and record.source_project.endswith(str(source_package))
    # Nothing is left behind on either side's disk.
    assert not (source_package / "transfers" / "outgoing" / result["transfer_id"]).exists()
    assert not (Path(db.path).parent / "transfers" / "incoming" / result["transfer_id"]).exists()


def test_a_dropped_send_lands_nothing_and_resumes_with_only_what_is_missing(client, db, tmp_path, far):
    source_package = open_source(tmp_path)
    source = db_manager.get_database(source_package)
    box = build_box(source, db, tmp_path)
    target_before = table_counts(db)
    machine = _pair(client)
    far.drop_after = 1

    stopped = _send(client, source_package, db, machine, [box.folder.id])

    assert stopped.status_code == 502, stopped.text
    said = stopped.json()["detail"]
    assert "1 of 2 objects" in said and "Nothing has landed" in said
    assert table_counts(db) == target_before and not _landed(db)
    [mirror] = source.all(TransferRecord)
    assert mirror.state.value == "sending" and "went to sleep" in mirror.error

    far.drop_after, far.puts = None, 0
    resumed = _send(client, source_package, db, machine, resume=mirror.id)

    assert resumed.status_code == 200, resumed.text
    assert resumed.json()["objects_sent"] == 1 and far.puts == 1  # only the object that had not arrived
    assert resumed.json()["transfer_id"] == mirror.id and len(resumed.json()["copies"]) == 1
    assert source.get(TransferRecord, mirror.id).state.value == "done"


def test_a_landing_that_fails_rolls_back_there_and_lands_on_retry_sending_nothing(client, db, tmp_path, far, monkeypatch):
    source_package = open_source(tmp_path)
    source = db_manager.get_database(source_package)
    box = build_box(source, db, tmp_path)
    target_before = table_counts(db)
    machine = _pair(client)
    real_save, saved = transfer_copy._save_row, []

    def fail_part_way(target_db, row):
        if len(saved) == 5:
            raise OSError("disk went away")
        real_save(target_db, row)
        saved.append(row.id)

    monkeypatch.setattr(transfer_copy, "_save_row", fail_part_way)
    stopped = _send(client, source_package, db, machine, [box.folder.id])

    assert stopped.status_code == 502 and "rolled back" in stopped.json()["detail"]
    assert len(saved) == 5 and table_counts(db) == target_before and not _landed(db)

    monkeypatch.setattr(transfer_copy, "_save_row", real_save)
    far.puts = 0
    resumed = _send(client, source_package, db, machine, resume=source.all(TransferRecord)[0].id)

    assert resumed.status_code == 200, resumed.text
    assert resumed.json()["objects_sent"] == 0 and far.puts == 0  # everything had arrived already
    assert [d.name for d in _landed(db) if d.id in resumed.json()["copies"]] == ["Box 1"]


def test_an_abandoned_copy_removes_what_arrived(client, db, tmp_path, far):
    source_package = open_source(tmp_path)
    source = db_manager.get_database(source_package)
    box = build_box(source, db, tmp_path)
    machine = _pair(client)
    far.drop_after = 1
    _send(client, source_package, db, machine, [box.folder.id])
    [mirror] = source.all(TransferRecord)
    incoming = Path(db.path).parent / "transfers" / "incoming" / mirror.id
    assert incoming.exists()

    gone = client.delete(f"/api/documents/transfer/incoming/{mirror.id}", headers={HEADER: str(Path(db.path).parent)})

    assert gone.status_code == 200 and gone.json()["removed"] == 1 and "abandoned" in gone.json()["said"]
    assert not incoming.exists()


def test_refused_in_words_sending_nothing(client, db, tmp_path, far, monkeypatch):
    source_package = open_source(tmp_path)
    source = db_manager.get_database(source_package)
    box = build_box(source, db, tmp_path)
    machine = _pair(client)

    no_yes = _send(client, source_package, db, machine, [box.folder.id], pages_may_leave=False)
    assert no_yes.status_code == 403 and "pages_may_leave" in no_yes.json()["detail"]
    unpaired = _send(client, source_package, db, "0" * 32, [box.folder.id])
    assert unpaired.status_code == 409 and "pair it first" in unpaired.json()["detail"]
    monkeypatch.setattr(remote, "contract", lambda: "another version")
    other = client.post("/api/documents/transfer/incoming", headers={HEADER: str(Path(db.path).parent)}, json={
        "transfer_id": "a" * 32, "manifest": {"library_id": "a" * 32, "generation": 1, "objects": []},
        "source_machine": "x", "source_project": "/x/X.fichero", "contract": "this version"})
    assert other.status_code == 409 and "different versions" in other.json()["detail"]
    assert far.puts == 0 and source.all(TransferRecord) == [] and not _landed(db)
    not_a_tailnet = client.post("/api/machines/pair", json={"address": "192.168.1.4", "code": "X"})
    assert not_a_tailnet.status_code == 422


def test_a_copy_to_another_machine_is_refused_when_the_app_allows_only_this_mac(client, db, tmp_path, far, monkeypatch):
    """#5831 (review 217): the request's own pages_may_leave=yes does not open a place the app keeps shut. Refused
    (403) in words before anything is looked up or sent, even for a machine that is not paired."""
    from fichero_server.recipes import places

    monkeypatch.setattr(places, "get_places", lambda: ["this-mac"])
    source_package = open_source(tmp_path)
    sent = []
    monkeypatch.setattr(remote, "contract", lambda: sent.append("contacted") or "x")

    refused = _send(client, source_package, db, "0" * 32)

    assert refused.status_code == 403, refused.text
    assert refused.json()["detail"] == places.refusal("another-mac")
    assert "another Mac of yours" in refused.json()["detail"]
    assert sent == []
