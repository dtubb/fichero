"""Regression tests for the content-pane save path (#4285 / #4286).

The DATA-LOSS pair: pasting artifact content into the document's Content
editor triggered a save the server answered with an unclassified non-2xx,
the client showed "Unexpected response from the server", and the edit was
discarded. Two server-side guarantees are pinned here:

1. PUT /api/documents/{id} ACCEPTS every artifact-pasted content shape the
   Mac editor produces — RTF source, large pastes, control characters, and
   the Swift OpenAPI client's null-filled optional fields.
2. A transient DuckDB write conflict (workflow writing while the user saves)
   is retried and, if persistent, surfaces as a typed 409 with a
   retry-guiding detail — never an unclassified 500.
"""

import asyncio
import json
from unittest.mock import patch

import duckdb
import pytest
from fastapi import HTTPException

from fichero_server.api.routes.document.documents import _run_document_write


def _mkdoc(client) -> str:
    r = client.post("/api/documents", json={"name": "paste-target.jpg"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.fixture(autouse=True)
def _fast_embed():
    """Skip the real re-embed after page_content edits — the reliability
    contract under test is HTTP acceptance, not embedding."""
    with patch("fichero_server.db.Database.embed", return_value=True):
        yield


class TestPastedContentIsAccepted:
    """PUT /api/documents/{id} must accept artifact-pasted payload shapes."""

    def test_rtf_source_from_artifact_paste_saves(self, client, db):
        doc_id = _mkdoc(client)
        rtf = (
            r"{\rtf1\ansi\deff0 {\fonttbl{\f0 Helvetica;}}"
            r"\f0\fs24 Pasted artifact text \'e9\par}"
        )
        r = client.put(f"/api/documents/{doc_id}", json={"page_content": rtf})
        assert r.status_code == 200, r.text
        assert r.json()["page_content"] == rtf

    def test_large_paste_saves(self, client, db):
        doc_id = _mkdoc(client)
        big = "Lorem ipsum dolor sit amet. " * 40000  # ~1.1 MB
        r = client.put(f"/api/documents/{doc_id}", json={"page_content": big})
        assert r.status_code == 200, r.text
        assert len(r.json()["page_content"]) == len(big)

    def test_control_characters_and_diacritics_save(self, client, db):
        doc_id = _mkdoc(client)
        weird = "line1 \x00 NUL é émigré \U0001f600"
        r = client.put(f"/api/documents/{doc_id}", json={"page_content": weird})
        assert r.status_code == 200, r.text
        assert r.json()["page_content"] == weird

    def test_swift_client_null_filled_optionals_save(self, client, db):
        """The Swift OpenAPI client serializes every omitted optional as an
        explicit JSON null — the update must apply only the non-null field."""
        doc_id = _mkdoc(client)
        payload = {
            "name": None, "parent_id": None, "node_kind": None,
            "doc_type": None, "file_type": None, "path": None,
            "page_content": "pasted text", "status": None, "is_read": None,
            "is_starred": None, "is_flagged": None,
            "exclude_from_processing": None, "metadata": None,
            "prototype_key": None, "position_x": None, "position_y": None,
            "position_z": None, "rotation_z": None, "scale": None,
            "z_index": None,
        }
        r = client.put(
            f"/api/documents/{doc_id}",
            content=json.dumps(payload),
            headers={"content-type": "application/json"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["page_content"] == "pasted text"
        assert body["name"] == "paste-target.jpg"  # null did not clobber

    def test_save_marks_user_edit_watermark(self, client, db):
        doc_id = _mkdoc(client)
        r = client.put(
            f"/api/documents/{doc_id}", json={"page_content": "edited by hand"}
        )
        assert r.status_code == 200
        assert "page_content_user_edited_at" in r.json()["metadata"]


class TestWriteConflictRetryAndClassification:
    """#4286: a concurrent-writer conflict must retry, then 409 — never 500."""

    def test_transient_conflict_is_retried_to_success(self):
        calls = {"n": 0}

        def flaky():
            calls["n"] += 1
            if calls["n"] < 3:
                raise duckdb.TransactionException("Conflict on update!")
            return "saved"

        result = asyncio.run(_run_document_write(flaky))
        assert result == "saved"
        assert calls["n"] == 3

    def test_persistent_conflict_maps_to_typed_409(self):
        def always_conflicts():
            raise duckdb.TransactionException("Conflict on update!")

        with pytest.raises(HTTPException) as excinfo:
            asyncio.run(_run_document_write(always_conflicts))
        assert excinfo.value.status_code == 409
        detail = str(excinfo.value.detail)
        assert "retry" in detail.lower()
        assert "nothing was saved" in detail

    def test_non_conflict_errors_still_propagate_unchanged(self):
        def boom():
            raise ValueError("not a conflict")

        with pytest.raises(ValueError, match="not a conflict"):
            asyncio.run(_run_document_write(boom))
