"""sharing.revoke-closes-the-stream (#5913), every stream: the change stream, the activity stream, the workflow-run stream, the
batch streams and the streaming search all end when the caller's paired device is revoked (review 339 / ## 590).

`end_on_revoke` is the one wrapper; a guard scan proves no streaming route leaves it out.
"""
from __future__ import annotations

import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from fichero_server.api import change_stream
from fichero_server.api.routes.system import changes
from fichero_server.api.routes.workflow_execution import core as run_stream
from fichero_server.execution.runner import WorkflowEventHub
from fichero_server.security import accounts, revocation
from _scan_files import scan_rglob

ROUTES = Path(change_stream.__file__).parent / "routes"


def _device(app_db, name):
    owner = next(iter(app_db.list_users()), None) or app_db.create_user(
        username="owner", display_name="Owner", password_hash=accounts.hash_password("x"), is_owner=True)
    return app_db.create_device(name=name, user_id=owner.id, token_hash=accounts.hash_token(accounts.new_session_token()))


def _request(device=None):
    return SimpleNamespace(state=SimpleNamespace(device=device, bootstrap_auth=device is None, user=None), scope={},
                           client=SimpleNamespace(host="198.51.100.20"), headers={})


@pytest.fixture(autouse=True)
def _the_app_db(app_db, monkeypatch):
    monkeypatch.setattr("fichero_server.db.app.get_app_db", lambda: app_db)


async def _forever():
    while True:
        await asyncio.sleep(0.01)
        yield "tick"


async def _take(stream, count):
    return [await asyncio.wait_for(anext(stream), 2) for _ in range(count)]


async def test_a_revoked_guests_stream_ends_and_another_devices_stays(app_db):
    guest, other = _device(app_db, "guest"), _device(app_db, "other")
    guest_stream = revocation.end_on_revoke(_request(guest), _forever())
    other_stream = revocation.end_on_revoke(_request(other), _forever())
    assert await _take(guest_stream, 1) == ["tick"] and await _take(other_stream, 1) == ["tick"]
    app_db.revoke_device(guest.id)
    with pytest.raises(StopAsyncIteration):
        await asyncio.wait_for(anext(guest_stream), 2)
    assert await _take(other_stream, 1) == ["tick"], "an untouched device keeps its stream"
    await other_stream.aclose()


async def test_a_stream_opened_after_the_revoke_ends_at_once(app_db):
    guest = _device(app_db, "guest")
    app_db.revoke_device(guest.id)  # the connect/revoke race: the registry is checked AFTER subscribing
    with pytest.raises(StopAsyncIteration):
        await asyncio.wait_for(anext(revocation.end_on_revoke(_request(guest), _forever())), 2)


async def test_the_hosts_own_window_is_passed_through(app_db):
    stream = revocation.end_on_revoke(_request(None), _forever())
    assert await _take(stream, 2) == ["tick", "tick"]
    await stream.aclose()


async def test_the_workflow_run_stream_route_ends_for_a_revoked_guest(app_db, monkeypatch):
    hub = WorkflowEventHub()
    monkeypatch.setattr(run_stream, "_get_workflow_state", lambda thread_id: {"events": hub})
    guest = _device(app_db, "guest")
    response = await run_stream.stream_workflow_events("thread-1", _request(guest))
    stream = response.body_iterator
    app_db.revoke_device(guest.id)
    with pytest.raises(StopAsyncIteration):
        await asyncio.wait_for(anext(stream), 5)


async def test_the_change_stream_refuses_a_device_revoked_as_it_connects(app_db, test_package):
    guest = _device(app_db, "guest")
    app_db.revoke_device(guest.id)
    before = change_stream._change_hub.subscriber_count(str(test_package))
    with pytest.raises(HTTPException) as refused:
        await changes.stream_library_changes(_request(guest), x_fichero_library_path=str(test_package))
    assert refused.value.status_code == 401
    assert change_stream._change_hub.subscriber_count(str(test_package)) == before, "the refused connection left no subscriber"


def test_every_streaming_route_goes_through_the_wrapper():
    """Guard: a StreamingResponse in api/routes either wraps its body in `end_on_revoke` or is the change stream, which ends
    through the hub's own `sharing.revoked` frame."""
    bare = []
    for path in sorted(scan_rglob(ROUTES, "*.py")):
        if path.name == "changes.py":
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "StreamingResponse":
                first = node.args[0] if node.args else None
                if not (isinstance(first, ast.Call) and getattr(first.func, "id", "") == "end_on_revoke"):
                    bare.append(f"{path.relative_to(ROUTES)}:{node.lineno}")
    assert not bare, f"a streaming route keeps a revoked guest's stream open: {bare}"
