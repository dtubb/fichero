"""sharing.remote-run-in-host-activity (#5732): a run started from a paired Mac names its person AND device.

Every run starter takes `started_by` from `started_by_for(ctx)`, so the host's Activity row (which shows
`started_by`) reads "alice on Alice's Mac" for a remote start and just the person for a local one.
"""

import importlib.util
from pathlib import Path

from fichero_server.actions.registry import ActionContext, started_by_for
from fichero_server.db import db_manager
from fichero_server.models import DocType, Document
from tests.unit.security.test_sharing_probe_2026_10_01 import (  # noqa: F401
    _bearer,
    _clear_pairing_state,
    _multiuser_on,
    _pair_as,
    harness,
)

# scripts/ is not a package: load the repo's scan helper by path (see test_scan_files_skips_nested_worktrees).
_SCAN = Path(__file__).resolve().parents[4] / "scripts" / "_scan_files.py"
_spec = importlib.util.spec_from_file_location("_scan_files", _SCAN)
assert _spec and _spec.loader
scan_files = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(scan_files)


def test_a_remote_start_names_the_person_and_the_device():
    ctx = ActionContext(actor="alice", device={"id": "d1", "name": "Alice's Mac"})
    assert started_by_for(ctx) == "alice on Alice's Mac"


def test_a_local_start_is_just_the_person_and_no_actor_is_the_owner():
    assert started_by_for(ActionContext(actor="alice")) == "alice"
    assert started_by_for(ActionContext(actor="")) == "owner"


def test_no_route_still_builds_started_by_from_the_bare_actor():
    routes = Path(__file__).resolve().parents[3] / "src" / "fichero_server" / "api" / "routes"
    offenders = [str(p.relative_to(routes)) for p in scan_files.scan_rglob(routes, "*.py")
                 if 'started_by=ctx.actor or "owner"' in p.read_text()]
    assert offenders == []


def test_a_run_started_from_a_paired_mac_is_a_row_in_the_hosts_activity_naming_who(harness, monkeypatch):
    """The host's Activity list (`GET /api/activity/jobs`) shows B's run with its starter, while it is queued."""
    _multiuser_on(harness, monkeypatch)
    dev = _pair_as(harness, "alice", "Alice's Mac")
    host, remote, alice = harness.host(), harness.remote(), _bearer(dev["device_token"])
    db = db_manager.get_database(harness.library)
    folder = Document(name="box", doc_type=DocType.folder)
    db.save(folder)

    started = remote.post("/api/find-documents/runs", json={"scope_ids": [folder.id]}, headers=alice)
    assert started.status_code == 200, started.text

    rows = {j["id"]: j for j in host.get("/api/activity/jobs").json()["jobs"]}
    assert rows[started.json()["job_id"]]["started_by"] == "alice on Alice's Mac"
