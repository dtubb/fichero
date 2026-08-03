"""document.set_language — a user's language correction, audited and durable (#2092).

The point is not that a user can type a language. It is that once they do, the
extraction pipeline cannot quietly undo it. A correction that re-extraction
erases is not a correction.
"""

from __future__ import annotations

import pytest

# Importing the route module registers document.set_language via @action.
import fichero_server.api.routes.document.documents  # noqa: F401
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.llm.language_policy import (
    SOURCE_USER,
    STATUS_UNKNOWN,
    apply_detected_language,
    is_user_set,
    parse_policy,
    resolve_language,
)
from fichero_server.models import ActionAudit, Document


@pytest.fixture
def document(db):
    doc = Document(name="Marshall diary page")
    db.save(doc)
    return doc


def _invoke(db, params):
    return registry.invoke(
        db, "document.set_language", params, ActionContext(actor="ui", library_path="")
    )


def test_setting_a_language_persists_it_as_a_user_assertion(db, document):
    result = _invoke(db, {"doc_id": document.id, "language": "Spanish"})

    assert result.ok is True
    stored = db.get(Document, document.id)
    assert stored.language == "Spanish"
    assert stored.language_meta["source"] == SOURCE_USER
    assert is_user_set(stored)


def test_the_correction_is_audited(db, document):
    result = _invoke(db, {"doc_id": document.id, "language": "Spanish"})

    audit = db.get(ActionAudit, result.audit_id)
    assert audit is not None
    assert audit.action_name == "document.set_language"
    assert audit.target_ids == [document.id]
    assert audit.after["language"] == "Spanish"


def test_a_user_language_survives_re_extraction(db, document):
    _invoke(db, {"doc_id": document.id, "language": "Spanish"})

    stored = db.get(Document, document.id)
    outcome = apply_detected_language(stored, "English", confidence=0.99)
    db.save(stored)

    assert outcome.applied is False
    assert outcome.conflict == {"user_language": "Spanish", "detected_language": "English"}
    assert db.get(Document, document.id).language == "Spanish"


def test_a_user_language_beats_the_global_default(db, document):
    _invoke(db, {"doc_id": document.id, "language": "Spanish"})
    stored = db.get(Document, document.id)

    resolution = resolve_language(document=stored, text="", policy=parse_policy("English"))

    assert resolution.language == "Spanish"
    assert resolution.source == SOURCE_USER


def test_undeterminable_is_an_assertion_not_an_absence(db, document):
    """"I looked and I cannot tell" is a finding, and is protected like one."""
    _invoke(db, {"doc_id": document.id, "undeterminable": True})

    stored = db.get(Document, document.id)
    assert stored.language is None
    assert stored.language_meta["status"] == STATUS_UNKNOWN
    assert stored.language_meta["source"] == SOURCE_USER

    assert apply_detected_language(stored, "English").applied is False
    assert stored.language is None


def test_omitting_both_clears_the_assertion_back_to_never_determined(db, document):
    _invoke(db, {"doc_id": document.id, "language": "Spanish"})
    _invoke(db, {"doc_id": document.id})

    stored = db.get(Document, document.id)
    assert stored.language is None
    assert stored.language_meta is None
    assert is_user_set(stored) is False
    # Cleared, so detection is free to run again — unlike `undeterminable`.
    assert apply_detected_language(stored, "English").applied is True


def test_a_blank_language_is_rejected_rather_than_stored(db, document):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as excinfo:
        _invoke(db, {"doc_id": document.id, "language": "   "})
    assert excinfo.value.status_code == 422


def test_an_unknown_document_is_a_404(db):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as excinfo:
        _invoke(db, {"doc_id": "no-such-document", "language": "Spanish"})
    assert excinfo.value.status_code == 404
