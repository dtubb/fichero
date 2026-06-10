"""Route-level tests for ``GET /api/changes/stream`` (#1863).

The hub primitives are already covered in ``test_change_stream.py``. These
tests exercise the FastAPI wrapper itself: initial open frame, event delivery
through the returned SSE stream, library scoping, and unsubscribe-on-close.
"""

from __future__ import annotations

import json

import pytest

from fichero.api import change_stream
from fichero.api.change_stream import emit_change
from fichero.api.routes import changes


class _FakeRequest:
    def __init__(self) -> None:
        self.disconnected = False

    async def is_disconnected(self) -> bool:
        return self.disconnected


def _patch_subscribe_to_capture_queue(monkeypatch):
    captured: dict[str, object] = {}
    original_subscribe = change_stream._change_hub.subscribe

    def _subscribe(library_path: str):
        queue = original_subscribe(library_path)
        captured["queue"] = queue
        return queue

    monkeypatch.setattr(change_stream._change_hub, "subscribe", _subscribe)
    return captured


class TestChangesStreamEndpoint:
    async def test_stream_emits_open_frame(self, test_package, monkeypatch):
        captured = _patch_subscribe_to_capture_queue(monkeypatch)
        request = _FakeRequest()
        library_path = str(test_package)
        before = change_stream._change_hub.subscriber_count(library_path)

        response = await changes.stream_library_changes(
            request,
            x_fichero_library_path=library_path,
        )
        stream = response.body_iterator

        try:
            first_frame = await anext(stream)

            assert first_frame == ": connected\n\n"
            assert change_stream._change_hub.subscriber_count(library_path) == before + 1
            assert "queue" in captured
        finally:
            await stream.aclose()

    async def test_stream_delivers_matching_library_change(
        self, test_package, monkeypatch
    ):
        captured = _patch_subscribe_to_capture_queue(monkeypatch)
        request = _FakeRequest()
        library_path = str(test_package)

        response = await changes.stream_library_changes(
            request,
            x_fichero_library_path=library_path,
        )
        stream = response.body_iterator

        try:
            first_frame = await anext(stream)
            assert first_frame == ": connected\n\n"

            emit_change(
                library_path,
                type="document.updated",
                document_ids=["doc-x"],
                actor="test",
            )

            second_frame = await anext(stream)
            assert second_frame.startswith("data: ")
            assert second_frame.endswith("\n\n")

            payload = json.loads(second_frame.removeprefix("data: ").strip())
            assert payload["type"] == "document.updated"
            assert payload["document_ids"] == ["doc-x"]
            assert payload["actor"] == "test"
        finally:
            await stream.aclose()

        queue = captured["queue"]
        assert queue is not None

    async def test_stream_ignores_other_library_change(
        self, test_package, monkeypatch
    ):
        captured = _patch_subscribe_to_capture_queue(monkeypatch)
        request = _FakeRequest()
        library_path = str(test_package)
        other_library_path = f"{library_path}.other"

        response = await changes.stream_library_changes(
            request,
            x_fichero_library_path=library_path,
        )
        stream = response.body_iterator

        try:
            first_frame = await anext(stream)
            assert first_frame == ": connected\n\n"

            emit_change(
                other_library_path,
                type="document.updated",
                document_ids=["doc-y"],
                actor="test",
            )

            queue = captured["queue"]
            assert queue is not None
            assert queue.empty()
            assert change_stream._change_hub.subscriber_count(other_library_path) == 0
        finally:
            await stream.aclose()

    async def test_stream_unsubscribes_when_client_disconnects(
        self, test_package, monkeypatch
    ):
        captured = _patch_subscribe_to_capture_queue(monkeypatch)
        request = _FakeRequest()
        library_path = str(test_package)
        before = change_stream._change_hub.subscriber_count(library_path)

        response = await changes.stream_library_changes(
            request,
            x_fichero_library_path=library_path,
        )
        stream = response.body_iterator

        first_frame = await anext(stream)
        assert first_frame == ": connected\n\n"
        assert change_stream._change_hub.subscriber_count(library_path) == before + 1

        request.disconnected = True

        with pytest.raises(StopAsyncIteration):
            await anext(stream)

        assert change_stream._change_hub.subscriber_count(library_path) == before
        assert "queue" in captured

    @pytest.mark.skip(
        reason="Hardcoded 30s keepalive timeout has no test seam; would require sleep."
    )
    async def test_stream_emits_keepalive_on_idle_timeout(self, test_package):
        """Keepalive branch is not cleanly testable without a timeout seam."""
        raise AssertionError("skipped")
