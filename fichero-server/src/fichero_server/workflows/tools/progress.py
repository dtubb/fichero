"""Progress-event helpers for long-running workflow tools."""

from __future__ import annotations

from typing import Any


async def emit_progress_event(
    progress_callback: Any,
    event_type: str,
    node_id: str,
    phase: str,
    index: int,
    total: int,
    *,
    message: str | None = None,
    error: str | None = None,
) -> None:
    """Emit one workflow progress event when the runner supplied a callback."""
    if not progress_callback:
        return
    payload: dict[str, Any] = {
        "file_path": phase,
        "file_index": index,
        "file_total": total,
        "progress": float(index) / max(total, 1),
    }
    if node_id:
        payload["node_id"] = node_id
    if message:
        payload["message"] = message
    if error:
        payload["error"] = error
    await progress_callback(event_type, payload)
