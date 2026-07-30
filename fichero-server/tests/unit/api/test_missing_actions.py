"""Unit tests for the 5 MISSING audited actions (#2018, EPIC #1848).

These are the capabilities the #2000-era inventory found had no single endpoint;
each is now a registered action reachable via ``registry.invoke`` (and the generic
``POST /api/actions/invoke``). Coverage per the project test bar — for every
action assert (a) the persisted effect, (b) an ActionAudit row (actor /
target_ids / before / after), (c) undo reverses it AND the redo / undo-of-undo
chain is sane (for undoable actions), (d) param validation rejects bad input,
(e) >=1 edge/failure case a naive impl would get wrong, and (f) emit_change fires
with the right type (spy monkeypatched at the SOURCE).

    annotation.duplicate  (undoable -> delete the copy)
    annotation.merge      (undoable -> annotation.unmerge, restores BOTH rows)
    annotation.relink     (undoable -> annotation.restore the before snapshot)
    search.reindex        (NOT undoable — idempotent index rebuild)
    workflow.run          (NOT undoable — single-shot create+execute a batch)

MANAGER-run (workers don't run pytest). Importing the route modules registers the
actions via the ``@action`` decorator at import time. The search.reindex test
monkeypatches ``Database.embed_entities`` / ``embed_claims`` so the action's
row-selection + audit are asserted WITHOUT pulling the heavy FastEmbed model (the
embedding itself is the proven wrapped method). The workflow.run test points a
fresh BatchManager at a temp duckdb and stubs the SSE generator (same approach as
``test_batch_actions.py``) so no live workflow runs.
"""

from __future__ import annotations

import asyncio
from datetime import datetime

import pytest
from pydantic import ValidationError
from fastapi import HTTPException

# Importing the route modules registers the actions on the process-global registry.
import fichero_server.api.routes.document.annotations  # noqa: F401
import fichero_server.api.routes.batch as batch_routes  # noqa: F401
import fichero_server.api.routes.search  # noqa: F401
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.models import ActionAudit, Document, DocType
from fichero_server.models.knowledge import (
    Annotation,
    AnnotationKind,
    KnowledgeClaim,
    KnowledgeEntity,
)
from fichero_server.workflows.batch import BatchEvent, BatchManager, BatchStatus


LIB = "/lib/test.fichero"


def _ctx() -> ActionContext:
    return ActionContext(actor="ui", library_path=LIB)


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def emit_spy(monkeypatch):
    """Spy on emit_change at the SOURCE module (where registry._emit imports it)."""
    calls: list[tuple] = []
    monkeypatch.setattr(
        "fichero_server.api.change_stream.emit_change",
        lambda *a, **k: calls.append((a, k)),
    )
    return calls


def _undo(db, audit_id, ctx):
    """Drive undo as the generic undo endpoint would: read the audit, ask the
    action for its inverse, invoke it. Returns (inverse_name, ActionResult)."""
    audit = db.get(ActionAudit, audit_id)
    reg = registry.get(audit.action_name)
    assert reg.undoable and reg.invert is not None, f"{audit.action_name} not undoable"
    inverse = reg.invert(audit.before, audit.after, ctx)
    assert inverse is not None
    inv_name, inv_params = inverse
    return inv_name, registry.invoke(db, inv_name, inv_params, ctx)


def _mk_doc(db, name="Doc", page_content=None) -> Document:
    doc = Document(name=name, doc_type=DocType.file, page_content=page_content)
    db.save(doc)
    return doc


def _mk_annotation(db, doc=None, **kw) -> Annotation:
    if doc is None:
        doc = _mk_doc(db)
    kw.setdefault("kind", AnnotationKind.note)
    ann = Annotation(document_id=doc.id, **kw)
    db.save(ann)
    return ann


# ===========================================================================
# Registry wiring — the 5 actions are discoverable + advertise the right flags
# ===========================================================================


class TestMissingActionsRegistered:
    def test_all_five_present(self):
        names = set(registry.names())
        assert {
            "annotation.duplicate",
            "annotation.merge",
            "annotation.relink",
            "search.reindex",
            "workflow.run",
        } <= names
        # the merge inverse is registered too
        assert "annotation.unmerge" in names

    def test_undoable_flags(self):
        assert registry.get("annotation.duplicate").undoable is True
        assert registry.get("annotation.merge").undoable is True
        assert registry.get("annotation.relink").undoable is True
        assert registry.get("annotation.unmerge").undoable is False
        assert registry.get("search.reindex").undoable is False
        assert registry.get("workflow.run").undoable is False


# ===========================================================================
# annotation.duplicate — copy with a fresh id, undo deletes the copy
# ===========================================================================


class TestAnnotationDuplicate:
    def test_duplicate_effect_audit_emit_and_undo(self, db, emit_spy):
        ctx = _ctx()
        doc = _mk_doc(db)
        src = _mk_annotation(
            db,
            doc=doc,
            kind=AnnotationKind.highlight,
            text="orig",
            color="#FFFF00",
            tags=["a", "b"],
            linked_claim_ids=["c1"],
            char_start=2,
            char_end=7,
        )
        result = registry.invoke(db, "annotation.duplicate", {"annotation_id": src.id}, ctx)
        assert result.ok and result.changed_domains == ["annotation"]
        new_id = result.result["id"]

        # (a) effect: a SEPARATE row exists, every field/link cloned
        assert new_id != src.id
        copy = db.get(Annotation, new_id)
        assert copy is not None
        assert copy.text == "orig"
        assert copy.color == "#FFFF00"
        assert copy.tags == ["a", "b"]
        assert copy.linked_claim_ids == ["c1"]
        assert copy.char_start == 2 and copy.char_end == 7
        assert copy.document_id == doc.id
        # the source is untouched
        assert db.get(Annotation, src.id) is not None

        # (b) audit row
        audit = db.get(ActionAudit, result.audit_id)
        assert audit.action_name == "annotation.duplicate"
        assert audit.actor == "ui"
        assert audit.target_ids == [new_id]
        assert audit.before is None
        assert audit.after["id"] == new_id

        # (f) emit fired as annotation.created with the scope doc id
        assert emit_spy[-1][1]["type"] == "annotation.created"
        assert doc.id in emit_spy[-1][1]["document_ids"]

        # (c) undo -> annotation.delete removes the copy, leaves the source
        inv, _ = _undo(db, result.audit_id, ctx)
        assert inv == "annotation.delete"
        assert db.get(Annotation, new_id) is None
        assert db.get(Annotation, src.id) is not None

    def test_duplicate_undo_then_redo_recreates_copy(self, db):
        """duplicate -> delete (undo) -> restore (redo) re-materializes the copy."""
        ctx = _ctx()
        src = _mk_annotation(db, text="x")
        res = registry.invoke(db, "annotation.duplicate", {"annotation_id": src.id}, ctx)
        copy_id = res.result["id"]
        del_name, del_res = _undo(db, res.audit_id, ctx)
        assert del_name == "annotation.delete"
        assert db.get(Annotation, copy_id) is None
        inv, _ = _undo(db, del_res.audit_id, ctx)
        assert inv == "annotation.restore"
        assert db.get(Annotation, copy_id) is not None

    def test_duplicate_unknown_id_404(self, db):
        with pytest.raises(HTTPException) as exc:
            registry.invoke(db, "annotation.duplicate", {"annotation_id": "ghost"}, _ctx())
        assert exc.value.status_code == 404

    def test_duplicate_validation_rejects_missing_id(self, db):
        with pytest.raises(ValidationError):
            registry.invoke(db, "annotation.duplicate", {}, _ctx())


# ===========================================================================
# annotation.merge — combine two, soft-delete absorbed, undo restores BOTH
# ===========================================================================


class TestAnnotationMerge:
    def test_merge_effect_audit_emit_and_undo(self, db, emit_spy):
        ctx = _ctx()
        doc = _mk_doc(db)
        target = _mk_annotation(
            db, doc=doc, text="T", tags=["x"], linked_claim_ids=["c1"],
            linked_entity_ids=["e1"], linked_note_ids=["n1"],
        )
        source = _mk_annotation(
            db, doc=doc, text="S", tags=["y"], linked_claim_ids=["c2"],
            linked_entity_ids=["e2"], linked_note_ids=["n2"],
        )
        result = registry.invoke(
            db, "annotation.merge", {"target_id": target.id, "source_id": source.id}, ctx
        )
        assert result.ok

        # (a) effect: target absorbs text + unions links/tags; source is gone
        merged = db.get(Annotation, target.id)
        assert merged.text == "T\n\nS"
        assert merged.tags == ["x", "y"]
        assert merged.linked_claim_ids == ["c1", "c2"]
        assert merged.linked_entity_ids == ["e1", "e2"]
        assert merged.linked_note_ids == ["n1", "n2"]
        assert db.get(Annotation, source.id) is None

        # (b) audit captures BOTH pre-merge snapshots + both target ids
        audit = db.get(ActionAudit, result.audit_id)
        assert audit.action_name == "annotation.merge"
        assert audit.target_ids == [target.id, source.id]
        assert audit.before["target"]["id"] == target.id
        assert audit.before["absorbed"]["id"] == source.id
        assert audit.before["target"]["text"] == "T"
        assert audit.before["absorbed"]["text"] == "S"

        # (f) emit
        assert emit_spy[-1][1]["type"] == "annotation.merged"
        assert doc.id in emit_spy[-1][1]["document_ids"]

        # (c) undo -> annotation.unmerge restores BOTH rows to pre-merge state
        inv, _ = _undo(db, result.audit_id, ctx)
        assert inv == "annotation.unmerge"
        back_target = db.get(Annotation, target.id)
        back_source = db.get(Annotation, source.id)
        assert back_target is not None and back_target.text == "T"
        assert back_target.linked_claim_ids == ["c1"]
        assert back_source is not None and back_source.text == "S"

    def test_merge_into_self_rejected_400(self, db):
        """A naive impl would happily delete the only row; merging into self is 400."""
        ctx = _ctx()
        ann = _mk_annotation(db, text="solo")
        with pytest.raises(HTTPException) as exc:
            registry.invoke(
                db, "annotation.merge", {"target_id": ann.id, "source_id": ann.id}, ctx
            )
        assert exc.value.status_code == 400
        # the row survives the rejected self-merge
        assert db.get(Annotation, ann.id) is not None

    def test_merge_missing_source_404(self, db):
        ctx = _ctx()
        target = _mk_annotation(db)
        with pytest.raises(HTTPException) as exc:
            registry.invoke(
                db, "annotation.merge", {"target_id": target.id, "source_id": "ghost"}, ctx
            )
        assert exc.value.status_code == 404

    def test_merge_missing_target_404(self, db):
        ctx = _ctx()
        source = _mk_annotation(db)
        with pytest.raises(HTTPException) as exc:
            registry.invoke(
                db, "annotation.merge", {"target_id": "ghost", "source_id": source.id}, ctx
            )
        assert exc.value.status_code == 404

    def test_merge_one_sided_text_does_not_inject_blank(self, db):
        """target has no text, source does -> merged text is just the source's
        (no leading '\\n\\n' a naive join would add)."""
        ctx = _ctx()
        target = _mk_annotation(db, text=None, kind=AnnotationKind.bookmark)
        source = _mk_annotation(db, text="only")
        registry.invoke(
            db, "annotation.merge", {"target_id": target.id, "source_id": source.id}, ctx
        )
        assert db.get(Annotation, target.id).text == "only"

    def test_merge_validation_rejects_missing_source(self, db):
        with pytest.raises(ValidationError):
            registry.invoke(db, "annotation.merge", {"target_id": "t"}, _ctx())


# ===========================================================================
# annotation.relink — update links / anchor target only, undo via restore
# ===========================================================================


class TestAnnotationRelink:
    def test_relink_effect_audit_emit_and_undo(self, db, emit_spy):
        ctx = _ctx()
        ann = _mk_annotation(db, text="keep me", linked_claim_ids=["old"])
        result = registry.invoke(
            db,
            "annotation.relink",
            {"annotation_id": ann.id, "linked_claim_ids": ["c1", "c2"], "linked_entity_ids": ["e1"]},
            ctx,
        )
        assert result.ok

        reloaded = db.get(Annotation, ann.id)
        assert reloaded.linked_claim_ids == ["c1", "c2"]
        assert reloaded.linked_entity_ids == ["e1"]
        # a relink leaves non-link fields untouched (exclude-unset)
        assert reloaded.text == "keep me"

        audit = db.get(ActionAudit, result.audit_id)
        assert audit.action_name == "annotation.relink"
        assert audit.target_ids == [ann.id]
        assert audit.before["linked_claim_ids"] == ["old"]
        assert audit.after["linked_claim_ids"] == ["c1", "c2"]
        assert emit_spy[-1][1]["type"] == "annotation.updated"

        # undo restores the prior links
        inv, _ = _undo(db, result.audit_id, ctx)
        assert inv == "annotation.restore"
        assert db.get(Annotation, ann.id).linked_claim_ids == ["old"]

    def test_relink_can_clear_links(self, db):
        """An explicit [] clears the list (distinct from 'field absent')."""
        ctx = _ctx()
        ann = _mk_annotation(db, linked_claim_ids=["c1"], linked_note_ids=["n1"])
        registry.invoke(
            db, "annotation.relink", {"annotation_id": ann.id, "linked_claim_ids": []}, ctx
        )
        reloaded = db.get(Annotation, ann.id)
        assert reloaded.linked_claim_ids == []
        # untouched list stays
        assert reloaded.linked_note_ids == ["n1"]

    def test_relink_retargets_anchor_with_scope_normalization(self, db):
        """Moving the anchor to a different document re-runs scope resolution."""
        ctx = _ctx()
        doc_a = _mk_doc(db, name="A")
        doc_b = _mk_doc(db, name="B")
        ann = _mk_annotation(db, doc=doc_a, text="t")
        registry.invoke(
            db, "annotation.relink", {"annotation_id": ann.id, "document_id": doc_b.id}, ctx
        )
        assert db.get(Annotation, ann.id).document_id == doc_b.id

    def test_relink_no_fields_rejected_400(self, db):
        """Relink with nothing to change is a 400, not a silent no-op audit."""
        ctx = _ctx()
        ann = _mk_annotation(db)
        with pytest.raises(HTTPException) as exc:
            registry.invoke(db, "annotation.relink", {"annotation_id": ann.id}, ctx)
        assert exc.value.status_code == 400

    def test_relink_unknown_id_404(self, db):
        with pytest.raises(HTTPException) as exc:
            registry.invoke(
                db, "annotation.relink", {"annotation_id": "ghost", "linked_claim_ids": ["c"]}, _ctx()
            )
        assert exc.value.status_code == 404

    def test_relink_validation_rejects_missing_id(self, db):
        with pytest.raises(ValidationError):
            registry.invoke(db, "annotation.relink", {"linked_claim_ids": ["c"]}, _ctx())


# ===========================================================================
# search.reindex — re-embed claims + entities in one audited pass
# ===========================================================================


class TestSearchReindex:
    @pytest.fixture
    def embed_spy(self, db, monkeypatch):
        """Count embed_entities/embed_claims calls WITHOUT the heavy FastEmbed
        model — asserts the action's row-selection + counts, not the vectoriser."""
        calls = {"entities": [], "claims": []}

        def _embed_entities(entities):
            calls["entities"].append([e.id for e in entities])
            return len(entities)

        def _embed_claims(claims):
            calls["claims"].append([c.id for c in claims])
            return len(claims)

        monkeypatch.setattr(db, "embed_entities", _embed_entities)
        monkeypatch.setattr(db, "embed_claims", _embed_claims)
        return calls

    def test_reindex_all_effect_audit_and_emit(self, db, embed_spy, emit_spy):
        ctx = _ctx()
        ent = KnowledgeEntity(canonical_name="Acme")
        claim = KnowledgeClaim(text="Acme exists")
        db.save(ent)
        db.save(claim)

        result = registry.invoke(db, "search.reindex", {}, ctx)
        assert result.ok and result.changed_domains == ["search"]
        # (a) effect: every entity + claim was passed to the embedders
        assert embed_spy["entities"] == [[ent.id]]
        assert embed_spy["claims"] == [[claim.id]]
        assert result.result == {"entities_indexed": 1, "claims_indexed": 1}

        # (b) audit row carries the counts as `after`
        audit = db.get(ActionAudit, result.audit_id)
        assert audit.action_name == "search.reindex"
        assert audit.after == {"entities_indexed": 1, "claims_indexed": 1}
        assert audit.before is None

        # (f) emit
        assert emit_spy[-1][1]["type"] == "search.reindexed"

    def test_reindex_subset_only_embeds_requested(self, db, embed_spy):
        """Passing ids embeds ONLY those rows (a naive impl would re-embed all)."""
        ctx = _ctx()
        e1 = KnowledgeEntity(canonical_name="One")
        e2 = KnowledgeEntity(canonical_name="Two")
        db.save(e1)
        db.save(e2)
        result = registry.invoke(db, "search.reindex", {"entity_ids": [e1.id]}, ctx)
        assert embed_spy["entities"] == [[e1.id]]
        assert result.result["entities_indexed"] == 1

    def test_reindex_skips_unknown_ids(self, db, embed_spy):
        """Unknown ids are dropped, not embedded as None (a naive impl would
        pass a None row into the vectoriser and crash)."""
        ctx = _ctx()
        e1 = KnowledgeEntity(canonical_name="Real")
        db.save(e1)
        registry.invoke(db, "search.reindex", {"entity_ids": [e1.id, "ghost"]}, ctx)
        assert embed_spy["entities"] == [[e1.id]]

    def test_reindex_empty_graph_is_zero_no_embed_call(self, db, embed_spy):
        """No rows -> 0/0 and the embedders are never called."""
        ctx = _ctx()
        result = registry.invoke(db, "search.reindex", {}, ctx)
        assert result.result == {"entities_indexed": 0, "claims_indexed": 0}
        assert embed_spy["entities"] == []
        assert embed_spy["claims"] == []

    def test_reindex_can_run_confirmed_embedding_space_migration(
        self,
        db,
        monkeypatch,
    ):
        calls = []

        def _migrate_embedding_space(**kwargs):
            calls.append(kwargs)
            return {
                "embedding_model_id": "BAAI/bge-m3|pooling=mean",
                "documents_indexed": 1,
                "entities_indexed": 2,
                "claims_indexed": 3,
                "before": {"embeddings": ["old"]},
                "after": {"embeddings": ["BAAI/bge-m3|pooling=mean"]},
            }

        monkeypatch.setattr(db, "migrate_embedding_space", _migrate_embedding_space)

        result = registry.invoke(
            db,
            "search.reindex",
            {
                "migrate_embedding_space": True,
                "confirm_embedding_migration": True,
                "include_documents": True,
                "include_entities": False,
                "include_claims": True,
            },
            _ctx(),
        )

        assert result.ok
        assert calls == [
            {
                "confirm": True,
                "include_documents": True,
                "include_entities": False,
                "include_claims": True,
            }
        ]
        assert result.result["documents_indexed"] == 1
        assert result.result["claims_indexed"] == 3

    def test_reindex_validation_rejects_bad_type(self, db):
        with pytest.raises(ValidationError):
            registry.invoke(db, "search.reindex", {"entity_ids": "not-a-list"}, _ctx())


# ===========================================================================
# workflow.run — single-shot create + execute a batch, returns the run id
# ===========================================================================


class TestWorkflowRun:
    @pytest.fixture
    def manager(self, tmp_path, monkeypatch):
        mgr = BatchManager(str(tmp_path / "workflow_run_test.duckdb"))
        monkeypatch.setattr(batch_routes, "_batch_manager", mgr)
        monkeypatch.setattr(batch_routes, "get_workflow_store", lambda: object())
        return mgr

    def _stub_execute(self, manager, monkeypatch, final_status=BatchStatus.COMPLETED):
        async def _stub(batch_id, store):
            b = await manager.get_batch(batch_id)
            b.status = final_status
            b.completed_at = datetime.now()
            await manager._save_batch(b)
            yield BatchEvent(batch_id=batch_id, event_type="batch_completed")

        monkeypatch.setattr(manager, "execute_batch", _stub)

    def test_run_creates_and_executes_returns_run_id(self, db, manager, emit_spy, monkeypatch):
        ctx = _ctx()
        self._stub_execute(manager, monkeypatch)
        params = {"workflow_id": "wf-1", "items": [{"input_text": "a"}, {"input_text": "b"}]}
        result = registry.invoke(db, "workflow.run", params, ctx)
        assert result.ok

        # (a) effect: a batch exists, was driven to COMPLETED, and the run id is returned
        run_id = result.result["run_id"]
        assert run_id and result.result["batch_id"] == run_id
        assert result.result["status"] == BatchStatus.COMPLETED.value
        persisted = _run(manager.get_batch(run_id))
        assert persisted is not None
        assert persisted.status == BatchStatus.COMPLETED
        assert len(persisted.items) == 2

        # (b) audit
        audit = db.get(ActionAudit, result.audit_id)
        assert audit.action_name == "workflow.run"
        assert audit.target_ids == [run_id]
        assert audit.before is None
        assert audit.after["batch_id"] == run_id

        # (f) emit
        assert emit_spy and emit_spy[-1][1]["type"] == "workflow.run"

    def test_run_is_not_undoable(self, db, manager, monkeypatch):
        reg = registry.get("workflow.run")
        assert reg.undoable is False and reg.invert is None

    def test_run_rejects_empty_items(self, db, manager):
        with pytest.raises(ValidationError):
            registry.invoke(db, "workflow.run", {"workflow_id": "wf-1", "items": []}, _ctx())

    def test_run_rejects_missing_workflow_id(self, db, manager):
        with pytest.raises(ValidationError):
            registry.invoke(db, "workflow.run", {"items": [{"x": 1}]}, _ctx())

    def test_run_rejects_out_of_range_concurrency(self, db, manager):
        with pytest.raises(ValidationError):
            registry.invoke(
                db,
                "workflow.run",
                {"workflow_id": "wf-1", "items": [{"x": 1}], "max_concurrent": 999},
                _ctx(),
            )
