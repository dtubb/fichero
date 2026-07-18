"""Coverage for optional workflow progress emission."""

from __future__ import annotations

import asyncio

from fichero.workflows.tools.progress import emit_progress_event


def test_emit_progress_event_is_noop_without_callback():
    asyncio.run(emit_progress_event(None, "progress", "node", "file.jpg", 1, 2))


def test_emit_progress_event_builds_bounded_payload():
    events = []

    async def callback(event_type, payload):
        events.append((event_type, payload))

    asyncio.run(
        emit_progress_event(
            callback,
            "workflow.progress",
            "node-1",
            "scan.jpg",
            3,
            2,
            message="done",
            error="warning",
        )
    )

    assert events == [
        (
            "workflow.progress",
            {
                "file_path": "scan.jpg",
                "file_index": 3,
                "file_total": 2,
                "progress": 1.5,
                "node_id": "node-1",
                "message": "done",
                "error": "warning",
            },
        )
    ]
