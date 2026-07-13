"""Route-level tests for ``GET /api/changes/stream`` (#1863).

The hub primitives are already covered in ``test_change_stream.py``. These
tests exercise the FastAPI wrapper itself: initial open frame, event delivery
through the returned SSE stream, library scoping, and unsubscribe-on-close.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from fichero.api import change_stream
from fichero.api.change_stream import _ChangeHub
from fichero.api.change_stream import emit_change
from fichero.api.routes import changes


class _FakeRequest:
    def __init__(self) -> None:
        self.disconnected = False
        # The route calls assert_library_read_authorized before opening the
        # stream (#2025 authz chokepoint). Mark the request as bootstrap-authed
        # so it takes the early-return path — these tests exercise the SSE
        # framing/delivery, not authorization (covered in test_authz_*).
        self.state = SimpleNamespace(bootstrap_auth=True, user=None)

    async def is_disconnected(self) -> bool:
        return self.disconnected


def _patch_subscribe_to_capture_queue(monkeypatch):
    captured: dict[str, object] = {}
    original_connect = change_stream._change_hub.connect

    def _connect(library_path: str, *, last_event_id: str | None = None):
        subscription = original_connect(library_path, last_event_id=last_event_id)
        captured["queue"] = subscription.queue
        return subscription

    monkeypatch.setattr(change_stream._change_hub, "connect", _connect)
    monkeypatch.setattr(changes._change_hub, "connect", _connect)
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
            assert second_frame.startswith("id: ")
            assert second_frame.endswith("\n\n")

            _, data_line = second_frame.split("\n", 1)
            payload = json.loads(data_line.removeprefix("data: ").strip())
            assert payload["type"] == "document.updated"
            assert payload["document_ids"] == ["doc-x"]
            assert payload["actor"] == "test"
            assert payload["event_id"] >= 1
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
        self, test_package, monkeypatch, caplog
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

        with caplog.at_level("INFO", logger="fichero.api.routes.changes"):
            with pytest.raises(StopAsyncIteration):
                await anext(stream)

        assert change_stream._change_hub.subscriber_count(library_path) == before
        assert "queue" in captured
        assert "disconnected cleanly" in caplog.text

    async def test_stream_replays_events_after_last_event_id(
        self, test_package, monkeypatch
    ):
        request = _FakeRequest()
        library_path = str(test_package)

        response = await changes.stream_library_changes(
            request,
            x_fichero_library_path=library_path,
        )
        stream = response.body_iterator

        try:
            assert await anext(stream) == ": connected\n\n"
            seen_ids: list[int] = []
            seen_types: list[str] = []
            for idx in range(5):
                emit_change(
                    library_path,
                    type=f"document.updated.{idx}",
                    document_ids=[f"doc-{idx}"],
                    actor="test",
                )
                frame = await anext(stream)
                id_line, data_line = frame.split("\n", 1)
                seen_ids.append(int(id_line.removeprefix("id: ")))
                payload = json.loads(data_line.removeprefix("data: ").strip())
                seen_types.append(payload["type"])
        finally:
            await stream.aclose()

        reconnect = await changes.stream_library_changes(
            _FakeRequest(),
            x_fichero_library_path=library_path,
            last_event_id=str(seen_ids[2]),
        )
        replay_stream = reconnect.body_iterator
        try:
            assert await anext(replay_stream) == ": connected\n\n"
            frame_one = await anext(replay_stream)
            frame_two = await anext(replay_stream)
        finally:
            await replay_stream.aclose()

        replay_payloads = []
        for frame in (frame_one, frame_two):
            _, data_line = frame.split("\n", 1)
            replay_payloads.append(json.loads(data_line.removeprefix("data: ").strip()))

        assert [payload["type"] for payload in replay_payloads] == seen_types[3:]

    async def test_stream_signals_full_resync_when_last_event_id_falls_out_of_ring(
        self, test_package, monkeypatch
    ):
        test_hub = _ChangeHub(replay_buffer_size=3)
        monkeypatch.setattr(change_stream, "_change_hub", test_hub)
        monkeypatch.setattr(changes, "_change_hub", test_hub)
        library_path = str(test_package)

        first_response = await changes.stream_library_changes(
            _FakeRequest(),
            x_fichero_library_path=library_path,
        )
        first_stream = first_response.body_iterator
        try:
            assert await anext(first_stream) == ": connected\n\n"
            seen_ids: list[int] = []
            for idx in range(5):
                emit_change(
                    library_path,
                    type=f"document.updated.{idx}",
                    document_ids=[f"doc-{idx}"],
                    actor="test",
                )
                frame = await anext(first_stream)
                id_line, _ = frame.split("\n", 1)
                seen_ids.append(int(id_line.removeprefix("id: ")))
        finally:
            await first_stream.aclose()

        reconnect = await changes.stream_library_changes(
            _FakeRequest(),
            x_fichero_library_path=library_path,
            last_event_id=str(seen_ids[0]),
        )
        replay_stream = reconnect.body_iterator
        try:
            assert await anext(replay_stream) == ": connected\n\n"
            resync_frame = await anext(replay_stream)
        finally:
            await replay_stream.aclose()

        _, data_line = resync_frame.split("\n", 1)
        payload = json.loads(data_line.removeprefix("data: ").strip())
        assert payload["type"] == "stream.resync_required"
        assert payload["replay_required"] is True
        assert payload["gap_reason"] == "last_event_id_too_old"
        assert payload["last_event_id"] == seen_ids[0]

    async def test_stream_checks_read_acl_before_subscribe(
        self, test_package, monkeypatch
    ):
        calls: list[tuple[object, str]] = []

        def _authz(request, library_path):
            calls.append((request, library_path))

        monkeypatch.setattr(changes, "assert_library_read_authorized", _authz)
        response = await changes.stream_library_changes(
            _FakeRequest(),
            x_fichero_library_path=str(test_package),
        )
        stream = response.body_iterator
        try:
            assert await anext(stream) == ": connected\n\n"
        finally:
            await stream.aclose()

        assert len(calls) == 1
        assert calls[0][1] == str(test_package)

    async def test_stream_emits_keepalive_on_idle_timeout(
        self, test_package, monkeypatch
    ):
        request = _FakeRequest()
        library_path = str(test_package)

        async def _timeout(awaitable, **_kwargs):
            awaitable.close()
            request.disconnected = True
            raise asyncio.TimeoutError

        monkeypatch.setattr(changes.asyncio, "wait_for", _timeout)

        response = await changes.stream_library_changes(
            request,
            x_fichero_library_path=library_path,
        )
        stream = response.body_iterator

        try:
            assert await anext(stream) == ": connected\n\n"
            assert await anext(stream) == ": keepalive\n\n"
            with pytest.raises(StopAsyncIteration):
                await anext(stream)
        finally:
            await stream.aclose()
