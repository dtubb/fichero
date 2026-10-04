"""A batch runs off the request, each item a run of the one runner, the batch their parent job (#5374).

Spec: docs/contributor_manual/specs/ui/activity-and-automatic-work.md: `activity.run.batch-off-the-request`
("a batch runs on the engine's work path, not on the API's event loop, survives the client
disconnecting, and writes a run record per item") and "What is deleted": "a batch is a parent job
whose children are run jobs". Written from the spec's text, and driven through the public surface:
a batch created with `POST /api/batches`, started with `POST /api/batches/{id}/execute` (its event
stream), followed with `GET /api/batches/{id}`, each item's run with
`GET /api/workflow-execution/threads/{thread}/status`, and the tree with `GET /api/activity/jobs/{id}`.
Only the model is a stub: a cloud vision model that answers from memory.
"""
from __future__ import annotations

import json
import threading

from tests.unit.jobs.test_runs_are_jobs import (  # noqa: F401
    _status, _tree, _wait_for, cloud, no_embedding_model, pages, workflow,
)


def _create(client, workflow, pages):
    r = client.post("/api/batches", json={
        "workflow_id": workflow.id, "max_concurrent": 2,
        "items": [{"selected_doc_ids": [page.id]} for page in pages]})
    assert r.status_code == 200, r.text
    return r.json()


def _batch(client, batch_id):
    r = client.get(f"/api/batches/{batch_id}")
    assert r.status_code == 200, r.text
    return r.json()


def _start_and_hang_up(client, batch_id):
    """Start the batch and read its first event, then disconnect, as a closed window would: as with
    a real server, every later `send` on the response fails (`OSError`), which is how a streaming
    response learns its client is gone. (The test client's own stream cannot do this: closing it
    lets the response run on.)"""
    import asyncio

    path = f"/api/batches/{batch_id}/execute"
    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "POST",
        "scheme": "http", "path": path, "raw_path": path.encode(), "query_string": b"", "root_path": "",
        "headers": [(k.lower().encode(), v.encode()) for k, v in client.headers.items()],
        "client": ("127.0.0.1", 50000), "server": ("127.0.0.1", 80),
    }
    first: list = []
    got_one = threading.Event()

    async def receive():
        if not hasattr(receive, "asked"):
            receive.asked = True
            return {"type": "http.request", "body": b"", "more_body": False}
        await asyncio.Event().wait()  # the client says nothing more

    async def send(message):
        if got_one.is_set():
            raise OSError("the client has gone")
        if message["type"] == "http.response.body" and message.get("body"):
            first.append(json.loads(message["body"].decode().strip()[5:]))
            got_one.set()

    def serve():
        try:
            asyncio.run(client.app(scope, receive, send))
        except Exception:  # noqa: BLE001 -- the response ending on the dead client is the point
            pass

    threading.Thread(target=serve, daemon=True).start()
    assert got_one.wait(30)
    return first[0]


def test_activity_run_batch_off_the_request__it_finishes_after_the_client_hangs_up(client, workflow, pages, cloud):
    """Behaviour `activity.run.batch-off-the-request`: a batch "survives the client disconnecting".
    The client reads the batch's first event and closes the stream while the model holds the first
    page; when the model answers, every item still finishes."""
    cloud.gate = threading.Event()
    batch = _create(client, workflow, pages)
    try:
        first = _start_and_hang_up(client, batch["batch_id"])
        assert first is not None and first["event_type"] == "batch_started"
        assert cloud.first_call.wait(30)
    finally:
        cloud.gate.set()
    assert _wait_for(lambda: _batch(client, batch["batch_id"])["status"] == "completed")
    assert _batch(client, batch["batch_id"])["completed_items"] == 3 and cloud.calls == 3


def test_activity_run_batch_off_the_request__each_item_is_a_run_with_its_record(client, workflow, pages, cloud):
    """Behaviour `activity.run.batch-off-the-request`: a batch "writes a run record per item": each
    item's run is a run of the one runner, followed and finished like any run."""
    batch = _create(client, workflow, pages)
    _start_and_hang_up(client, batch["batch_id"])
    assert _wait_for(lambda: _batch(client, batch["batch_id"])["status"] == "completed")
    for item in _batch(client, batch["batch_id"])["items"]:
        assert _status(client, item["thread_id"]) == "completed"


def test_activity_jobs_are_a_tree__a_batch_is_the_parent_of_its_runs(client, workflow, pages, cloud):
    """Spec, "What is deleted": "a batch is a parent job whose children are run jobs". The batch's
    row holds one run per item, each with its steps and pages, and the pages roll up to it."""
    batch = _create(client, workflow, pages)
    _start_and_hang_up(client, batch["batch_id"])
    assert _wait_for(lambda: _batch(client, batch["batch_id"])["status"] == "completed")
    tree = _tree(client, batch["batch_id"])
    assert (tree["kind"], tree["state"]) == ("batch", "done")
    runs = {child["id"] for child in tree["children"]}
    assert runs == {item["thread_id"] for item in _batch(client, batch["batch_id"])["items"]}
    assert all(child["kind"] == "workflow" for child in tree["children"])
    assert (tree["done"], tree["total"]) == (3, 3)
