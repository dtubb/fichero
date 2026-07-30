"""Persisting KG rows and announcing them are the same act (#4392).

The Knowledge Graph inspector observes `ClaimStore.changeToken` and reloads
when it bumps. Nine tools emitted after writing; `kg_writer` — the node that
persists when `persist_kg` is OFF, i.e. the catalogue preset's DEFAULT path —
did not. So on the default path rows landed in the database, nothing was
published, and the pane kept showing what it loaded when the document was
opened. The same extraction through a `persist_kg`-ON preset updated fine,
because that path emitted: two paths silently disagreeing about whether a
write is observable.

Emission now lives in the shared write helpers, so a caller cannot persist KG
rows without announcing them. These tests pin that property at the helper (the
thing that must not regress), at the callers that used to emit for themselves
(they must not now double-emit), and at `kg_writer` (the caller that was
missed, which must now work without having been touched).

Nothing here skips.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from tests.integration._seedlib import seed

from fichero_server.db import db_manager
from fichero_server.models import DocType, Document, FileType
from fichero_server.workflows.tools import extractors as extractors_module


@pytest.fixture
def library(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("FICHERO_SKIP_DEFAULT_WORKFLOWS", "1")
    package = tmp_path / "kg-emit.fichero"
    seed(package)
    db = db_manager.get_database(package)
    doc = Document(
        id="kg-emit-doc-1",
        name="page-1.txt",
        path=str(tmp_path / "page-1.txt"),
        doc_type=DocType.file,
        file_type=FileType.text,
        page_content="Regression Person in Regression Place.",
    )
    db.save(doc)
    return db, doc.id


@pytest.fixture
def captured_emits(monkeypatch):
    """Record every change event the KG emitter publishes."""
    events: list[dict] = []

    def _record(library_path, **kwargs):
        events.append({"library_path": library_path, **kwargs})

    monkeypatch.setattr(
        "fichero_server.api.change_stream.emit_change", _record
    )
    return events


def _people_section():
    for section in extractors_module._SECTIONS:
        if section.get("schema_key") == "people":
            return section
    raise AssertionError("no 'people' section in _SECTIONS — fixture is stale")


def _write_people(db, doc_id, names):
    items = [
        {"name": name, "description": f"{name} appears in the source."}
        for name in names
    ]
    return extractors_module._write_kg_rows(
        db, _people_section(), items, doc_id, page_label="1"
    )


class TestTheSharedWriteHelperAnnouncesItsRows:
    def test_writing_kg_rows_emits_entity_and_claim_changes(
        self, library, captured_emits
    ):
        db, doc_id = library
        entity_ids, claim_ids = _write_people(db, doc_id, ["Regression Person"])
        assert entity_ids or claim_ids, "precondition: the write produced rows"

        types = [event.get("type") for event in captured_emits]
        assert "entity.updated" in types, (
            "persisting KG rows published no entity.updated — the inspector's "
            "change token never bumps and the pane goes stale (#4392)"
        )
        assert "claim.updated" in types

    def test_emitted_ids_are_the_rows_actually_written(
        self, library, captured_emits
    ):
        """Not a superset, not a blanket 'something changed'."""
        db, doc_id = library
        entity_ids, claim_ids = _write_people(
            db, doc_id, ["Alpha Person", "Beta Person"]
        )

        emitted_entities = [
            eid
            for event in captured_emits
            if event.get("type") == "entity.updated"
            for eid in (event.get("entity_ids") or [])
        ]
        emitted_claims = [
            cid
            for event in captured_emits
            if event.get("type") == "claim.updated"
            for cid in (event.get("claim_ids") or [])
        ]
        assert sorted(emitted_entities) == sorted(entity_ids)
        assert sorted(emitted_claims) == sorted(claim_ids)

    def test_the_written_document_is_named(self, library, captured_emits):
        db, doc_id = library
        _write_people(db, doc_id, ["Regression Person"])
        emitted_docs = [
            did
            for event in captured_emits
            if event.get("type") == "document.updated"
            for did in (event.get("document_ids") or [])
        ]
        assert doc_id in emitted_docs

    def test_a_write_that_produced_no_rows_emits_nothing(
        self, library, captured_emits
    ):
        """Failure path: an empty item list is not a change. Emitting on it
        would bump every open inspector for nothing."""
        db, doc_id = library
        entity_ids, claim_ids = extractors_module._write_kg_rows(
            db, _people_section(), [], doc_id
        )
        assert (entity_ids, claim_ids) == ([], [])
        assert [e for e in captured_emits if e.get("type") in
                {"entity.updated", "claim.updated"}] == [], (
            "an empty write announced a change that did not happen"
        )


class TestEveryCallerIsCorrectByConstruction:
    def test_kg_writer_emits_without_calling_the_emitter_itself(
        self, library, captured_emits
    ):
        """The node the original defect was about.

        `kg_writer` still contains no emit call of its own — that is the
        point. It is correct because the write path it uses announces for it.
        """
        import inspect

        from fichero_server.workflows.tools import kg_writer as kg_writer_module

        source = inspect.getsource(kg_writer_module)
        assert "emit_workflow_kg_changes" not in source, (
            "kg_writer regained its own emit call — the fix was supposed to "
            "make it correct WITHOUT one, so this now double-emits (#4392)"
        )

        db, doc_id = library
        section_name = _people_section().get("name")
        state = {"library_path": str(Path(db.path).parent), "task_id": "kg-writer-run"}
        from fichero_server.llm import LLMConfig

        asyncio.run(
            kg_writer_module.kg_writer(
                inputs={
                    "kg_payload": [
                        {
                            "section_name": section_name,
                            "items": [
                                {
                                    "name": "Regression Person",
                                    "description": "appears in the source.",
                                }
                            ],
                            "target_doc_id": doc_id,
                            "page_label": "1",
                        }
                    ]
                },
                state=state,
                llm_config=LLMConfig(provider="$small", model="$small"),
            )
        )

        types = [event.get("type") for event in captured_emits]
        assert "claim.updated" in types and "entity.updated" in types, (
            "the catalogue preset's default KG path still writes silently — "
            "this is the exact #4392 symptom"
        )

    def test_no_caller_emits_the_same_rows_twice(self, library, captured_emits):
        """Side effect of moving emission: a caller that kept its own emit
        would publish every row twice. One write, one announcement."""
        db, doc_id = library
        entity_ids, _ = _write_people(db, doc_id, ["Regression Person"])

        entity_events = [
            event for event in captured_emits if event.get("type") == "entity.updated"
        ]
        assert len(entity_events) == 1, (
            f"{len(entity_events)} entity.updated events for one write — a "
            "caller is emitting on top of the shared write path (#4392)"
        )
        assert sorted(entity_events[0].get("entity_ids") or []) == sorted(entity_ids)


class TestGuardrailPinsTheSharedEmission:
    """Concentrating emission in one helper creates one place to break it."""

    def test_the_shared_write_paths_are_covered_by_the_ratchet(self):
        from scripts.check_emit_change_coverage import (  # noqa: PLC0415
            REQUIRED_TERMINAL_EMITS,
            scan_required_terminal_emits,
        )

        pinned = {rel_path for rel_path, _ in REQUIRED_TERMINAL_EMITS}
        assert (
            "fichero-server/src/fichero_server/workflows/tools/extractors.py" in pinned
        ), "deleting _write_kg_rows' emit would silence every KG write at once"
        assert (
            "fichero-server/src/fichero_server/workflows/tools/extract_all.py" in pinned
        ), "the custom-entity write path is a second, separately-pinned emitter"
        assert scan_required_terminal_emits() == []
