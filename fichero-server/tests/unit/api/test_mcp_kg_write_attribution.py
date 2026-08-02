"""#4485: MCP KG writes — authenticated author, audited, emitted.

Who asserted a claim is the difference between evidence and hearsay. The
route honoured a client-supplied ``created_by`` — a client could record that
someone asserted a claim they never asserted, undetectably — and saved with
no MutationLog and no change emit, so the write was invisible to the audit
trail and to every other client.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch


from fichero_server.api.routes.mcp.tools import (
    KnowledgeClaimCreateRequest,
    KnowledgeEntityUpsertRequest,
    mcp_knowledge_claim_create,
    mcp_knowledge_entity_upsert,
)
from fichero_server.models.knowledge import MutationLog


def _db() -> MagicMock:
    db = MagicMock()
    db.path = Path("/tmp/Lib.fichero/fichero.duckdb")
    db.saved = []
    db.save.side_effect = db.saved.append
    return db


def _saved_of(db: MagicMock, kind):
    return [obj for obj in db.saved if isinstance(obj, kind)]


class TestClaimAuthorCannotBeForged:
    def _create(self, db, *, body_created_by: str, actor: str):
        request = KnowledgeClaimCreateRequest(
            text="Istmina is on the San Juan",
            source_document_id="doc-1",
            created_by=body_created_by,
        )
        with patch("fichero_server.api.change_stream.emit_change") as emit:
            result = asyncio.run(
                mcp_knowledge_claim_create(request, db=db, actor=actor)
            )
        return result, emit

    def test_body_created_by_is_ignored(self):
        """FAILS without the fix: the route wrote request.created_by."""
        db = _db()
        result, _ = self._create(db, body_created_by="Ann", actor="agent")
        assert result.claim["created_by"] == "agent", (
            "a client recorded that Ann asserted a claim she never asserted — "
            "authorship must derive from authenticated request state"
        )

    def test_claim_create_writes_a_mutation_log(self):
        """FAILS without the fix: the write produced no record at all."""
        db = _db()
        result, _ = self._create(db, body_created_by="mcp", actor="agent")
        logs = _saved_of(db, MutationLog)
        assert len(logs) == 1
        log = logs[0]
        assert log.entity_type == "KnowledgeClaim"
        assert log.entity_id == result.claim_id
        assert log.operation.value == "create"
        assert log.before_state is None
        assert log.created_by == "agent"

    def test_claim_create_emits_to_the_change_stream(self):
        db = _db()
        result, emit = self._create(db, body_created_by="mcp", actor="agent")
        assert emit.called, "a mutation that does not emit is invisible (#4427)"
        kwargs = emit.call_args[1]
        assert kwargs["claim_ids"] == [result.claim_id]
        assert kwargs["actor"] == "agent"


class TestEntityCreateIsAccountable:
    def test_entity_create_writes_log_and_emits(self):
        """The upsert's CREATE branch saved with no log and no emit while the
        UPDATE branch logged (#4415) — an agent-created entity was
        untraceable. Same contract for both now."""
        db = _db()
        db.get.return_value = None  # no existing entity: CREATE branch
        request = KnowledgeEntityUpsertRequest(
            canonical_name="Chocó", entity_type="location"
        )
        with patch("fichero_server.api.change_stream.emit_change") as emit:
            result = asyncio.run(
                mcp_knowledge_entity_upsert(request, db=db, actor="agent")
            )
        logs = _saved_of(db, MutationLog)
        assert len(logs) == 1
        assert logs[0].entity_type == "KnowledgeEntity"
        assert logs[0].operation.value == "create"
        assert logs[0].created_by == "agent"
        assert emit.called
        assert emit.call_args[1]["entity_ids"] == [result.entity_id]

    def test_log_failure_is_loud_but_does_not_fail_the_write(self, caplog):
        db = _db()
        real_append = db.saved.append

        def _save(obj):
            if isinstance(obj, MutationLog):
                raise RuntimeError("disk full")
            real_append(obj)

        db.save.side_effect = _save
        request = KnowledgeClaimCreateRequest(
            text="t", source_document_id="doc-1"
        )
        with patch("fichero_server.api.change_stream.emit_change"):
            result = asyncio.run(
                mcp_knowledge_claim_create(request, db=db, actor="agent")
            )
        assert result.success
        assert any("mutation log FAILED" in r.message for r in caplog.records), (
            "a silent audit failure is how a guardrail stops existing"
        )
