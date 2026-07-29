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

from fichero_server.db import Database
from fichero_server.models import DocType, Document, Status
from fichero_server.workflows.completion import (
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


class TestCollectProcessedDocumentIdsPageParents:
    """#2219: per-page fan-out emits only page children; parent must be included."""

    def test_includes_parent_id_for_page_children(self):
        final_state = {
            "outputs": {
                "files-node": {
                    "documents": [
                        {"id": "page-1", "doc_type": "page", "parent_id": "parent-pdf"},
                        {"id": "page-2", "doc_type": "page", "parent_id": "parent-pdf"},
                    ]
                }
            }
        }
        ids = collect_processed_document_ids(final_state)
        assert "page-1" in ids
        assert "page-2" in ids
        assert "parent-pdf" in ids

    def test_does_not_include_folder_parent_for_file_children(self):
        # Regular file docs inside a folder must NOT bubble their folder's
        # id into the completed set — only page children should.
        final_state = {
            "outputs": {
                "files-node": {
                    "documents": [
                        {"id": "file-1", "doc_type": "file", "parent_id": "folder-abc"},
                    ]
                }
            }
        }
        ids = collect_processed_document_ids(final_state)
        assert "file-1" in ids
        assert "folder-abc" not in ids


class TestCompleteRunDocumentsPageParent:
    """#2219: parent file doc must be completed after per-page fan-out transcription."""

    def test_completes_pending_parent_when_explicitly_in_ids(self, temp_db):
        parent = Document(name="scan.pdf", path="/scan.pdf", status=Status.pending)
        temp_db.save(parent)
        pages = [
            Document(
                name=f"scan.pdf - Page {i}",
                doc_type=DocType.page,
                parent_id=parent.id,
                sequence=i,
                status=Status.processing,
            )
            for i in (1, 2, 3, 4)
        ]
        for page in pages:
            temp_db.save(page)

        # Simulate what collect_processed_document_ids produces for per-page
        # fan-out: page child IDs + the parent ID (added via parent_id tracking).
        run_doc_ids = {p.id for p in pages} | {parent.id}
        updated = complete_run_documents(temp_db, run_doc_ids)

        assert temp_db.get(Document, parent.id).status == Status.completed
        for page in pages:
            assert temp_db.get(Document, page.id).status == Status.completed
        assert updated == 5

    def test_pending_child_found_via_query_not_flipped(self, temp_db):
        # An untouched page sibling (pending) found via db.query must NOT be
        # completed — only the ones explicitly in document_ids get the pending→
        # completed flip.
        parent = Document(name="scan.pdf", path="/scan.pdf", status=Status.processing)
        temp_db.save(parent)
        processed_page = Document(
            name="scan.pdf - Page 1",
            doc_type=DocType.page,
            parent_id=parent.id,
            sequence=1,
            status=Status.processing,
        )
        skipped_page = Document(
            name="scan.pdf - Page 2",
            doc_type=DocType.page,
            parent_id=parent.id,
            sequence=2,
            status=Status.pending,
        )
        temp_db.save(processed_page)
        temp_db.save(skipped_page)

        # Only parent id is in document_ids (simulating old-style non-fan-out).
        complete_run_documents(temp_db, {parent.id})

        assert temp_db.get(Document, parent.id).status == Status.completed
        assert temp_db.get(Document, processed_page.id).status == Status.completed
        assert temp_db.get(Document, skipped_page.id).status == Status.pending


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

    def test_leaves_completed_docs_unchanged(self, temp_db):
        # A KG-only run over already-completed docs must not re-flip them.
        done = Document(name="done.txt", path="/d.txt", status=Status.completed)
        temp_db.save(done)

        updated = complete_run_documents(temp_db, {done.id})

        assert updated == 0
        assert temp_db.get(Document, done.id).status == Status.completed

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
