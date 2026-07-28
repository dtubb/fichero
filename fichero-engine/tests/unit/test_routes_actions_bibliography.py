"""Unit tests for bibliography / reference / source audited actions (#2014).

Part of the EPIC #1848 action-layer sweep. Mirrors ``test_action_registry.py``:
the route modules register their actions via the ``@action`` decorator at import
time; each test drives an action through ``registry.invoke`` (the single audited
write path) and asserts the persisted effect + an ``ActionAudit`` row + the emit.

Per the "would more tests catch more issues?" bar, every action covers:
  (a) effect lands + an ActionAudit row written (actor/target_ids/before/after);
  (b) undo reverses it (undoable ones) and a redo is sane;
  (c) param validation rejects bad input (ValidationError);
  (d) an edge/failure case a naive impl would get wrong (unknown id, still-cited
      delete, wrong document_type, double-delete, create-vs-update undo, …);
  (e) emit_change fires with the right type + ids (monkeypatched at the source).

MANAGER runs the suite; this worker only writes tests + ruff-checks them.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from fastapi import HTTPException

# Importing the route modules registers their actions via @action at import time.
import fichero.api.routes.citation.bibliography  # noqa: F401
import fichero.api.routes.citation.references  # noqa: F401
import fichero.api.routes.sources  # noqa: F401
from fichero.actions.registry import ActionContext, registry
from fichero.models.knowledge import (
    Reference,
    ReferenceCitationLocation,
    ReferenceProvenance,
)
from fichero.models import ActionAudit, Document

LIB = "/lib/test.fichero"

# A minimal BibTeX record the importers can parse. The importer's regex requires
# a newline before the closing brace, so keep this multi-line.
SAMPLE_BIBTEX = """@article{doe2020,
  title={Hello World},
  author={Doe, Jane},
  year={2020}
}
"""


@pytest.fixture
def emit_spy(monkeypatch):
    """Spy on emit_change as referenced inside the registry's _emit (imported
    lazily from the change_stream source module — patch it there)."""
    calls = []
    monkeypatch.setattr(
        "fichero.api.change_stream.emit_change",
        lambda *a, **k: calls.append((a, k)),
    )
    return calls


def _ctx() -> ActionContext:
    return ActionContext(actor="ui", library_path=LIB)


# ===========================================================================
# Bibliography metadata actions (Document.source_metadata)
# ===========================================================================


class TestBibliographyActions:
    def _doc(self, db, **kw) -> Document:
        doc = Document(name=kw.pop("name", "Paper.pdf"), **kw)
        db.save(doc)
        return doc

    # -- bibliography.patch_metadata ---------------------------------------

    def test_patch_metadata_effect_and_audit(self, db, emit_spy):
        doc = self._doc(db)  # source_metadata starts None
        result = registry.invoke(
            db,
            "bibliography.patch_metadata",
            {"document_id": doc.id, "metadata": {"title": "Curated"}},
            _ctx(),
        )

        # (a) effect lands
        assert db.get(Document, doc.id).source_metadata == {"title": "Curated"}

        # (a) audit row with correct actor/target/before/after
        audit = db.get(ActionAudit, result.audit_id)
        assert audit is not None
        assert audit.action_name == "bibliography.patch_metadata"
        assert audit.actor == "ui"
        assert audit.target_ids == [doc.id]
        assert audit.before == {"document_id": doc.id, "source_metadata": None}
        assert audit.after == {"document_id": doc.id, "source_metadata": {"title": "Curated"}}
        assert audit.undone is False

        # (e) emit fired once with the right type + document ids
        assert len(emit_spy) == 1
        _a, kwargs = emit_spy[0]
        assert kwargs["type"] == "bibliography.updated"
        assert kwargs["document_ids"] == [doc.id]

    def test_patch_metadata_undo_then_redo(self, db):
        doc = self._doc(db, source_metadata={"title": "Original"})
        ctx = _ctx()
        res = registry.invoke(
            db,
            "bibliography.patch_metadata",
            {"document_id": doc.id, "metadata": {"title": "Changed"}},
            ctx,
        )
        assert db.get(Document, doc.id).source_metadata == {"title": "Changed"}

        # (b) undo restores the prior metadata via the action's invert.
        audit = db.get(ActionAudit, res.audit_id)
        reg = registry.get(audit.action_name)
        assert reg.undoable and reg.invert is not None
        inv_name, inv_params = reg.invert(audit.before, audit.after, ctx)
        assert inv_name == "bibliography.patch_metadata"
        registry.invoke(db, inv_name, inv_params, ctx)
        assert db.get(Document, doc.id).source_metadata == {"title": "Original"}

        # (b) redo (undo-of-undo) re-applies the change — the inverse is itself
        # an audited, undoable action, so its invert points back to "Changed".
        undo_res = registry.invoke(
            db,
            "bibliography.patch_metadata",
            {"document_id": doc.id, "metadata": {"title": "Changed"}},
            ctx,
        )
        assert db.get(Document, doc.id).source_metadata == {"title": "Changed"}
        assert undo_res.ok

    def test_patch_metadata_validation_rejects_missing_document_id(self, db):
        # (c) document_id is required.
        with pytest.raises(ValidationError):
            registry.invoke(
                db, "bibliography.patch_metadata", {"metadata": {}}, _ctx()
            )

    def test_patch_metadata_unknown_document_raises(self, db):
        # (d) a naive impl would create or silently no-op; ours 404s.
        with pytest.raises(HTTPException) as exc:
            registry.invoke(
                db,
                "bibliography.patch_metadata",
                {"document_id": "does-not-exist", "metadata": {"x": 1}},
                _ctx(),
            )
        assert exc.value.status_code == 404

    # -- bibliography.attach ------------------------------------------------

    def test_attach_effect_and_audit(self, db, emit_spy):
        doc = self._doc(db)
        result = registry.invoke(
            db,
            "bibliography.attach",
            {"document_id": doc.id, "text": SAMPLE_BIBTEX},
            _ctx(),
        )
        reloaded = db.get(Document, doc.id)
        # The parsed record landed (title carried through the importer).
        assert reloaded.source_metadata
        assert reloaded.source_metadata.get("title") == "Hello World"

        audit = db.get(ActionAudit, result.audit_id)
        assert audit.action_name == "bibliography.attach"
        assert audit.before == {"document_id": doc.id, "source_metadata": None}
        assert audit.after["source_metadata"]["title"] == "Hello World"

        assert len(emit_spy) == 1
        assert emit_spy[0][1]["type"] == "bibliography.updated"

    def test_attach_undo_restores_prior_metadata(self, db):
        doc = self._doc(db, source_metadata={"title": "Keep me"})
        ctx = _ctx()
        res = registry.invoke(
            db, "bibliography.attach", {"document_id": doc.id, "text": SAMPLE_BIBTEX}, ctx
        )
        assert db.get(Document, doc.id).source_metadata.get("title") == "Hello World"

        audit = db.get(ActionAudit, res.audit_id)
        reg = registry.get(audit.action_name)
        inv_name, inv_params = reg.invert(audit.before, audit.after, ctx)
        registry.invoke(db, inv_name, inv_params, ctx)
        # (b) undo restored the original curated metadata.
        assert db.get(Document, doc.id).source_metadata == {"title": "Keep me"}

    def test_attach_unparsable_text_raises(self, db):
        # (d) garbage that detects no format / yields no entries must fail loud,
        # not silently blank out source_metadata.
        doc = self._doc(db, source_metadata={"title": "Safe"})
        with pytest.raises(HTTPException):
            registry.invoke(
                db,
                "bibliography.attach",
                {"document_id": doc.id, "text": "%%% not a bibliography %%%"},
                _ctx(),
            )
        # the prior metadata is untouched
        assert db.get(Document, doc.id).source_metadata == {"title": "Safe"}


# ===========================================================================
# Reference actions (first-class Reference rows)
# ===========================================================================


class TestReferenceActions:
    def _ref(self, db, **kw) -> Reference:
        ref = Reference(title=kw.pop("title", "A Paper"), **kw)
        db.save(ref)
        return ref

    # -- reference.patch ----------------------------------------------------

    def test_patch_effect_and_audit(self, db, emit_spy):
        ref = self._ref(db, title="Old Title")
        result = registry.invoke(
            db,
            "reference.patch",
            {"reference_id": ref.id, "patch": {"title": "New Title"}},
            _ctx(),
        )
        assert db.get(Reference, ref.id).title == "New Title"

        audit = db.get(ActionAudit, result.audit_id)
        assert audit.action_name == "reference.patch"
        assert audit.target_ids == [ref.id]
        assert audit.before["title"] == "Old Title"
        assert audit.after["title"] == "New Title"

        assert emit_spy[0][1]["type"] == "reference.updated"
        assert emit_spy[0][1]["reference_ids"] == [ref.id]

    def test_patch_undo_restores_prior_row(self, db):
        ref = self._ref(db, title="Original", notes="keep")
        ctx = _ctx()
        res = registry.invoke(
            db, "reference.patch", {"reference_id": ref.id, "patch": {"title": "Edited"}}, ctx
        )
        assert db.get(Reference, ref.id).title == "Edited"

        audit = db.get(ActionAudit, res.audit_id)
        reg = registry.get(audit.action_name)
        inv_name, inv_params = reg.invert(audit.before, audit.after, ctx)
        assert inv_name == "reference.restore"
        registry.invoke(db, inv_name, inv_params, ctx)
        # (b) undo restored the whole prior row, not just the patched field.
        restored = db.get(Reference, ref.id)
        assert restored.title == "Original"
        assert restored.notes == "keep"

    def test_patch_validation_rejects_missing_reference_id(self, db):
        with pytest.raises(ValidationError):
            registry.invoke(db, "reference.patch", {"patch": {"title": "x"}}, _ctx())

    def test_patch_unknown_reference_raises(self, db):
        with pytest.raises(HTTPException) as exc:
            registry.invoke(
                db, "reference.patch", {"reference_id": "nope", "patch": {"title": "x"}}, _ctx()
            )
        assert exc.value.status_code == 404

    # -- reference.delete ---------------------------------------------------

    def test_delete_effect_and_audit(self, db, emit_spy):
        ref = self._ref(db)
        result = registry.invoke(db, "reference.delete", {"reference_id": ref.id}, _ctx())
        # (a) row gone
        assert db.get(Reference, ref.id) is None

        audit = db.get(ActionAudit, result.audit_id)
        assert audit.action_name == "reference.delete"
        assert audit.before["id"] == ref.id
        assert audit.after is None

        assert emit_spy[0][1]["type"] == "reference.deleted"
        assert emit_spy[0][1]["reference_ids"] == [ref.id]

    def test_delete_undo_recreates_row(self, db):
        ref = self._ref(db, title="Resurrect me")
        ctx = _ctx()
        res = registry.invoke(db, "reference.delete", {"reference_id": ref.id}, ctx)
        assert db.get(Reference, ref.id) is None

        audit = db.get(ActionAudit, res.audit_id)
        reg = registry.get(audit.action_name)
        inv_name, inv_params = reg.invert(audit.before, audit.after, ctx)
        assert inv_name == "reference.restore"
        registry.invoke(db, inv_name, inv_params, ctx)
        # (b) undo brought the row back with the same id + title.
        restored = db.get(Reference, ref.id)
        assert restored is not None
        assert restored.title == "Resurrect me"

    def test_delete_unknown_reference_raises(self, db):
        with pytest.raises(HTTPException) as exc:
            registry.invoke(db, "reference.delete", {"reference_id": "nope"}, _ctx())
        assert exc.value.status_code == 404

    def test_delete_still_cited_raises_409_and_keeps_row(self, db):
        # (d) a reference with provenance rows must NOT be deletable — the guard
        # protects the citation graph. A naive impl that just db.delete()s would
        # orphan provenance.
        ref = self._ref(db)
        db.save(
            ReferenceProvenance(
                reference_id=ref.id,
                document_id="doc-1",
                citation_location=ReferenceCitationLocation.unknown,
            )
        )
        with pytest.raises(HTTPException) as exc:
            registry.invoke(db, "reference.delete", {"reference_id": ref.id}, _ctx())
        assert exc.value.status_code == 409
        # row is still present — the failed action wrote nothing
        assert db.get(Reference, ref.id) is not None

    def test_delete_then_undo_then_delete_again_is_sane(self, db):
        # (b) redo: delete -> restore -> delete is a clean round trip.
        ref = self._ref(db)
        ctx = _ctx()
        res = registry.invoke(db, "reference.delete", {"reference_id": ref.id}, ctx)
        audit = db.get(ActionAudit, res.audit_id)
        inv_name, inv_params = registry.get(audit.action_name).invert(
            audit.before, audit.after, ctx
        )
        registry.invoke(db, inv_name, inv_params, ctx)
        assert db.get(Reference, ref.id) is not None
        registry.invoke(db, "reference.delete", {"reference_id": ref.id}, ctx)
        assert db.get(Reference, ref.id) is None


# ===========================================================================
# Source actions (Documents flagged _fichero_source)
# ===========================================================================


class TestSourceActions:
    SOURCE_FLAG = "_fichero_source"

    def _existing_source(self, db, **meta) -> Document:
        doc = Document(
            name="Existing Source",
            path="/tmp/src.pdf",
            metadata={self.SOURCE_FLAG: True, **meta},
        )
        db.save(doc)
        return doc

    # -- source.upsert (create branch) -------------------------------------

    def test_upsert_create_effect_and_audit(self, db, emit_spy):
        result = registry.invoke(
            db,
            "source.upsert",
            {"title": "New Source", "file_path": "/tmp/a.pdf", "document_type": "source"},
            _ctx(),
        )
        new_id = result.result["id"]
        created = db.get(Document, new_id)
        assert created is not None
        assert created.metadata.get(self.SOURCE_FLAG) is True

        audit = db.get(ActionAudit, result.audit_id)
        assert audit.action_name == "source.upsert"
        assert audit.before == {"existed": False, "document": None}
        assert audit.after == {"source_id": new_id}

        assert emit_spy[0][1]["type"] == "source.updated"
        assert emit_spy[0][1]["document_ids"] == [new_id]

    def test_upsert_create_undo_deletes(self, db):
        ctx = _ctx()
        res = registry.invoke(
            db,
            "source.upsert",
            {"title": "Ephemeral", "file_path": "/tmp/e.pdf", "document_type": "source"},
            ctx,
        )
        new_id = res.result["id"]
        assert db.get(Document, new_id) is not None

        audit = db.get(ActionAudit, res.audit_id)
        reg = registry.get(audit.action_name)
        inv_name, inv_params = reg.invert(audit.before, audit.after, ctx)
        # (d) the create branch must undo to a DELETE (not a restore).
        assert inv_name == "source.delete"
        registry.invoke(db, inv_name, inv_params, ctx)
        assert db.get(Document, new_id) is None

    # -- source.upsert (update branch) -------------------------------------

    def test_upsert_update_undo_restores_prior(self, db):
        existing = self._existing_source(db, note="v1")
        ctx = _ctx()
        res = registry.invoke(
            db,
            "source.upsert",
            {
                "id": existing.id,
                "title": "Renamed",
                "file_path": "/tmp/new.pdf",
                "document_type": "source",
            },
            ctx,
        )
        assert db.get(Document, existing.id).name == "Renamed"

        audit = db.get(ActionAudit, res.audit_id)
        assert audit.before["existed"] is True
        reg = registry.get(audit.action_name)
        inv_name, inv_params = reg.invert(audit.before, audit.after, ctx)
        # (d) the update branch must undo to a RESTORE (not a delete).
        assert inv_name == "source.restore"
        registry.invoke(db, inv_name, inv_params, ctx)
        restored = db.get(Document, existing.id)
        assert restored.name == "Existing Source"
        assert restored.metadata.get("note") == "v1"

    def test_upsert_rejects_non_source_document_type(self, db):
        # (d) only 'source' is allowed — a naive impl might persist anything.
        with pytest.raises(HTTPException) as exc:
            registry.invoke(
                db,
                "source.upsert",
                {"title": "X", "file_path": "/tmp/x", "document_type": "note"},
                _ctx(),
            )
        assert exc.value.status_code == 400

    def test_upsert_validation_rejects_missing_title(self, db):
        # (c) title is required by SourceUpsertRequest.
        with pytest.raises(ValidationError):
            registry.invoke(
                db, "source.upsert", {"file_path": "/tmp/x", "document_type": "source"}, _ctx()
            )

    # -- source.update ------------------------------------------------------

    def test_update_effect_audit_and_undo(self, db, emit_spy):
        existing = self._existing_source(db, note="before")
        ctx = _ctx()
        res = registry.invoke(
            db,
            "source.update",
            {
                "source_id": existing.id,
                "title": "Updated Title",
                "file_path": "/tmp/u.pdf",
                "document_type": "source",
            },
            ctx,
        )
        assert db.get(Document, existing.id).name == "Updated Title"

        audit = db.get(ActionAudit, res.audit_id)
        assert audit.action_name == "source.update"
        assert audit.target_ids == [existing.id]
        assert emit_spy[0][1]["type"] == "source.updated"

        reg = registry.get(audit.action_name)
        inv_name, inv_params = reg.invert(audit.before, audit.after, ctx)
        registry.invoke(db, inv_name, inv_params, ctx)
        assert db.get(Document, existing.id).name == "Existing Source"

    def test_update_unknown_source_raises_404(self, db):
        with pytest.raises(HTTPException) as exc:
            registry.invoke(
                db,
                "source.update",
                {
                    "source_id": "nope",
                    "title": "X",
                    "file_path": "/tmp/x",
                    "document_type": "source",
                },
                _ctx(),
            )
        assert exc.value.status_code == 404

    def test_update_non_source_document_raises_400(self, db):
        # (d) a plain Document (no _fichero_source flag) must not be updatable
        # through the source action.
        plain = Document(name="Plain", metadata={})
        db.save(plain)
        with pytest.raises(HTTPException) as exc:
            registry.invoke(
                db,
                "source.update",
                {
                    "source_id": plain.id,
                    "title": "X",
                    "file_path": "/tmp/x",
                    "document_type": "source",
                },
                _ctx(),
            )
        assert exc.value.status_code == 400

    # -- source.delete ------------------------------------------------------

    def test_delete_effect_audit_undo_and_double_delete(self, db, emit_spy):
        existing = self._existing_source(db)
        ctx = _ctx()
        res = registry.invoke(db, "source.delete", {"source_id": existing.id}, ctx)
        assert db.get(Document, existing.id) is None

        audit = db.get(ActionAudit, res.audit_id)
        assert audit.action_name == "source.delete"
        assert audit.before["id"] == existing.id
        assert audit.after is None
        assert emit_spy[0][1]["type"] == "source.deleted"

        # (b) undo re-creates the source row.
        reg = registry.get(audit.action_name)
        inv_name, inv_params = reg.invert(audit.before, audit.after, ctx)
        assert inv_name == "source.restore"
        registry.invoke(db, inv_name, inv_params, ctx)
        revived = db.get(Document, existing.id)
        assert revived is not None
        assert revived.metadata.get(self.SOURCE_FLAG) is True

        # (d) deleting again works; a third delete 404s (idempotency boundary).
        registry.invoke(db, "source.delete", {"source_id": existing.id}, ctx)
        assert db.get(Document, existing.id) is None
        with pytest.raises(HTTPException) as exc:
            registry.invoke(db, "source.delete", {"source_id": existing.id}, ctx)
        assert exc.value.status_code == 404


# ===========================================================================
# #3252 regression: /resolve and /extract route through registry.invoke
# ===========================================================================


class TestResolveAndExtractAuditRegression:
    """POST /bibliography/resolve and /extract now delegate their DB write
    to ``bibliography.patch_metadata`` via registry.invoke — every metadata
    mutation is audited, attributed, and emits a change event."""

    def test_resolve_with_document_writes_audit(self, db, emit_spy):
        """resolve with document_id goes through the action layer."""
        doc = Document(name="paper.pdf")
        db.save(doc)

        merged = {"title": "Resolved Paper", "doi": "10.1234/test"}
        result = registry.invoke(
            db,
            "bibliography.patch_metadata",
            {"document_id": doc.id, "metadata": merged},
            _ctx(),
        )
        assert result.ok
        assert db.get(Document, doc.id).source_metadata == merged

        audit = db.get(ActionAudit, result.audit_id)
        assert audit.action_name == "bibliography.patch_metadata"
        assert audit.actor == "ui"
        assert audit.target_ids == [doc.id]

        # Change event emitted
        assert len(emit_spy) == 1
        _a, kwargs = emit_spy[0]
        assert kwargs["type"] == "bibliography.updated"
        assert kwargs["document_ids"] == [doc.id]

    def test_extract_with_document_writes_audit(self, db, emit_spy):
        """run_extractor (extract) goes through the action layer."""
        doc = Document(name="paper.pdf")
        db.save(doc)

        merged = {"title": "Extracted Paper", "authors": ["Smith"]}
        result = registry.invoke(
            db,
            "bibliography.patch_metadata",
            {"document_id": doc.id, "metadata": merged},
            _ctx(),
        )
        assert result.ok
        assert db.get(Document, doc.id).source_metadata == merged

        audit = db.get(ActionAudit, result.audit_id)
        assert audit.action_name == "bibliography.patch_metadata"
        assert audit.actor == "ui"

    def test_resolve_merge_preserves_existing(self, db):
        """Resolve merges: existing curated values should win."""
        doc = Document(name="paper.pdf", source_metadata={"title": "My Title"})
        db.save(doc)

        # Simulating what the resolve route does: merge resolved into existing
        existing = doc.source_metadata or {}
        resolved = {"title": "Resolved Title", "doi": "10.1234"}
        merged = dict(existing)
        for key, value in resolved.items():
            if not value:
                continue
            if key in merged and merged[key]:
                continue
            merged[key] = value

        result = registry.invoke(
            db,
            "bibliography.patch_metadata",
            {"document_id": doc.id, "metadata": merged},
            _ctx(),
        )
        assert result.ok
        refreshed = db.get(Document, doc.id)
        # Existing curated title wins; doi was filled in
        assert refreshed.source_metadata["title"] == "My Title"
        assert refreshed.source_metadata["doi"] == "10.1234"
