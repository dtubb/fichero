"""Tests for per-document workflow completion (#1282).

Tool nodes leave documents in ``Status.processing`` mid-pipeline; the workflow
boundary flips the run's own documents (and their page children) to
``Status.completed`` once everything finishes — so the per-page green check no
longer appears after just the first step.
"""

import shutil
import tempfile
from pathlib import Path

import pytest

from fichero.db import Database
from fichero.models import DocType, Document, Status
from fichero.workflows.completion import (
    collect_processed_document_ids,
    complete_run_documents,
)


@pytest.fixture
def temp_db():
    tmpdir = tempfile.mkdtemp()
    db = Database(Path(tmpdir) / "test.duckdb")
    yield db
    db.close()
    shutil.rmtree(tmpdir)


class TestCollectProcessedDocumentIds:
    def test_collects_from_source_node_outputs(self):
        final_state = {
            "outputs": {
                "files-node": {
                    "documents": [{"id": "doc-a"}, {"id": "doc-b"}],
                },
                "transcribe-node": {"text": "..."},  # no documents key
            }
        }
        assert collect_processed_document_ids(final_state) == {"doc-a", "doc-b"}

    def test_collects_top_level_and_parallel_document(self):
        final_state = {
            "documents": [{"id": "doc-top"}],
            "parallel_document": {"id": "doc-par"},
        }
        assert collect_processed_document_ids(final_state) == {"doc-top", "doc-par"}

    def test_ignores_malformed_entries_and_non_dicts(self):
        assert collect_processed_document_ids(None) == set()
        assert collect_processed_document_ids({"outputs": "nope"}) == set()
        assert collect_processed_document_ids(
            {"outputs": {"n": {"documents": [{}, {"id": ""}, "str"]}}}
        ) == set()


class TestCompleteRunDocuments:
    def test_flips_processing_to_completed(self, temp_db):
        doc = Document(name="a.txt", path="/a.txt", status=Status.processing)
        temp_db.save(doc)

        updated = complete_run_documents(temp_db, {doc.id})

        assert updated == 1
        assert temp_db.get(Document, doc.id).status == Status.completed

    def test_completes_page_children_of_parent(self, temp_db):
        parent = Document(name="report.pdf", path="/r.pdf", status=Status.processing)
        temp_db.save(parent)
        pages = [
            Document(
                name=f"report.pdf - Page {i}",
                doc_type=DocType.page,
                parent_id=parent.id,
                sequence=i,
                status=Status.processing,
            )
            for i in (1, 2)
        ]
        for page in pages:
            temp_db.save(page)

        # Only the parent id surfaces in the run outputs; children follow.
        updated = complete_run_documents(temp_db, {parent.id})

        assert updated == 3
        assert temp_db.get(Document, parent.id).status == Status.completed
        for page in pages:
            assert temp_db.get(Document, page.id).status == Status.completed

    def test_leaves_non_processing_docs_untouched(self, temp_db):
        # A KG-only run over already-completed docs must not be disturbed.
        done = Document(name="done.txt", path="/d.txt", status=Status.completed)
        pending = Document(name="pending.txt", path="/p.txt", status=Status.pending)
        temp_db.save(done)
        temp_db.save(pending)

        updated = complete_run_documents(temp_db, {done.id, pending.id})

        assert updated == 0
        assert temp_db.get(Document, done.id).status == Status.completed
        assert temp_db.get(Document, pending.id).status == Status.pending

    def test_does_not_complete_unprocessed_folder_siblings(self, temp_db):
        # A folder member that this run did not touch stays pending, even though
        # its (processed) sibling is completed — the processing guard scopes it.
        folder = Document(name="folder", doc_type=DocType.folder, status=Status.processing)
        temp_db.save(folder)
        processed = Document(
            name="touched.txt", parent_id=folder.id, status=Status.processing
        )
        untouched = Document(
            name="skipped.txt", parent_id=folder.id, status=Status.pending
        )
        temp_db.save(processed)
        temp_db.save(untouched)

        complete_run_documents(temp_db, {folder.id})

        assert temp_db.get(Document, processed.id).status == Status.completed
        assert temp_db.get(Document, untouched.id).status == Status.pending

    def test_empty_input_is_noop(self, temp_db):
        assert complete_run_documents(temp_db, set()) == 0

    def test_records_workflow_run_provenance(self, temp_db):
        doc = Document(name="a.txt", path="/a.txt", status=Status.processing)
        temp_db.save(doc)

        updated = complete_run_documents(
            temp_db,
            {doc.id},
            workflow_run={
                "thread_id": "thread-123",
                "workflow_id": "wf-123",
                "workflow_name": "Transcribe",
                "model": "gpt-4o-mini",
                "result": {"status": "completed", "pages": 1},
                "started_at": "2026-05-31T10:00:00Z",
                "completed_at": "2026-05-31T10:02:30Z",
            },
        )

        loaded = temp_db.get(Document, doc.id)
        assert updated == 1
        assert loaded is not None
        assert loaded.workflow_runs == [
            {
                "thread_id": "thread-123",
                "workflow_id": "wf-123",
                "workflow_name": "Transcribe",
                "model": "gpt-4o-mini",
                "result": {"status": "completed", "pages": 1},
                "started_at": "2026-05-31T10:00:00Z",
                "completed_at": "2026-05-31T10:02:30Z",
            }
        ]
