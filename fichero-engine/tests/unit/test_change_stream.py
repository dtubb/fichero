"""Unit tests for the per-library change-stream hub (#1863).

Covers the hub primitives (subscribe → emit_change → queue delivery, per-library
isolation, unsubscribe) plus a light route test that the entity-merge endpoint
actually emits a change event.

The hub tests exercise the queues synchronously: ``asyncio.Queue.put_nowait`` /
``get_nowait`` manipulate the internal deque without needing a running event
loop, so no async runner is required.
"""

from __future__ import annotations

import asyncio
from datetime import datetime

import pytest

from fichero.api import change_stream
from fichero.api.change_stream import (
    ChangeEvent,
    _ChangeHub,
    emit_change,
    format_change_sse,
)
from fichero.knowledge_models import EntityType, KnowledgeEntity


# ---------------------------------------------------------------------------
# Hub primitives
# ---------------------------------------------------------------------------


class TestChangeHub:
    def test_subscribe_then_emit_delivers_event(self):
        hub = _ChangeHub()
        queue = hub.subscribe("/lib/A.fichero")

        event = ChangeEvent(type="entity.updated", entity_ids=["e1"])
        delivered = hub.emit("/lib/A.fichero", event)

        assert delivered == 1
        assert queue.get_nowait() is event

    def test_per_library_isolation(self):
        hub = _ChangeHub()
        queue_a = hub.subscribe("/lib/A.fichero")
        queue_b = hub.subscribe("/lib/B.fichero")

        hub.emit("/lib/A.fichero", ChangeEvent(type="entity.merged"))

        # A receives; B stays empty.
        assert queue_a.get_nowait().type == "entity.merged"
        with pytest.raises(asyncio.QueueEmpty):
            queue_b.get_nowait()

    def test_fan_out_to_multiple_windows(self):
        hub = _ChangeHub()
        q1 = hub.subscribe("/lib/A.fichero")
        q2 = hub.subscribe("/lib/A.fichero")

        delivered = hub.emit("/lib/A.fichero", ChangeEvent(type="entity.deleted"))

        assert delivered == 2
        assert q1.get_nowait().type == "entity.deleted"
        assert q2.get_nowait().type == "entity.deleted"

    def test_unsubscribe_stops_delivery(self):
        hub = _ChangeHub()
        queue = hub.subscribe("/lib/A.fichero")
        assert hub.subscriber_count("/lib/A.fichero") == 1

        hub.unsubscribe("/lib/A.fichero", queue)
        assert hub.subscriber_count("/lib/A.fichero") == 0

        delivered = hub.emit("/lib/A.fichero", ChangeEvent(type="entity.updated"))
        assert delivered == 0
        with pytest.raises(asyncio.QueueEmpty):
            queue.get_nowait()

    def test_emit_to_library_with_no_subscribers_is_noop(self):
        hub = _ChangeHub()
        assert hub.emit("/lib/nobody.fichero", ChangeEvent(type="entity.updated")) == 0


# ---------------------------------------------------------------------------
# emit_change convenience + event schema
# ---------------------------------------------------------------------------


class TestEmitChange:
    def test_emit_change_builds_event_with_all_fields(self, monkeypatch):
        captured: list[tuple[str, ChangeEvent]] = []
        monkeypatch.setattr(
            change_stream._change_hub,
            "emit",
            lambda lib, event: captured.append((lib, event)) or 1,
        )

        emit_change(
            "/lib/A.fichero",
            type="entity.merged",
            entity_ids=["e1", "e2"],
            claim_ids=["c1"],
            actor="ui",
            origin_window="win-7",
        )

        assert len(captured) == 1
        lib, event = captured[0]
        assert lib == "/lib/A.fichero"
        assert event.type == "entity.merged"
        assert event.entity_ids == ["e1", "e2"]
        assert event.claim_ids == ["c1"]
        assert event.actor == "ui"
        assert event.origin_window == "win-7"
        assert event.ts  # default timestamp populated

    def test_emit_change_blank_library_is_noop(self, monkeypatch):
        called = []
        monkeypatch.setattr(
            change_stream._change_hub, "emit", lambda *a: called.append(a)
        )
        emit_change("", type="entity.updated")
        assert called == []

    def test_emit_change_never_raises(self, monkeypatch):
        def boom(*_a, **_k):
            raise RuntimeError("hub exploded")

        monkeypatch.setattr(change_stream._change_hub, "emit", boom)
        # Best-effort contract: must swallow the error, not propagate.
        emit_change("/lib/A.fichero", type="entity.updated")

    def test_format_change_sse_frame(self):
        frame = format_change_sse(ChangeEvent(type="entity.updated", entity_ids=["e1"]))
        assert frame.startswith("data: ")
        assert frame.endswith("\n\n")
        assert '"type":"entity.updated"' in frame


# ---------------------------------------------------------------------------
# Light route test: the merge endpoint emits a change event
# ---------------------------------------------------------------------------


def _make_entity(db, name: str) -> KnowledgeEntity:
    entity = KnowledgeEntity(
        canonical_name=name,
        entity_type=EntityType.person,
        aliases=[name.lower()],
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    db.save(entity)
    return entity


class TestMergeEmitsChange:
    def test_merge_endpoint_calls_emit_change(self, client, db, test_package, monkeypatch):
        captured: list[dict] = []

        def _spy(library_path, **kwargs):
            captured.append({"library_path": library_path, **kwargs})

        # Patch the name as imported into the route module.
        monkeypatch.setattr(
            "fichero.api.routes.kg_entity_curation.emit_change", _spy
        )

        absorber = _make_entity(db, "Alice")
        absorbed = _make_entity(db, "Alicia")

        r = client.post(
            "/api/kg/entity-curation/merge",
            json={
                "absorbing_entity_id": absorber.id,
                "absorbed_entity_ids": [absorbed.id],
            },
        )
        assert r.status_code == 200

        assert len(captured) == 1
        call = captured[0]
        assert call["library_path"] == str(test_package)
        assert call["type"] == "entity.merged"
        assert absorber.id in call["entity_ids"]
        assert absorbed.id in call["entity_ids"]
