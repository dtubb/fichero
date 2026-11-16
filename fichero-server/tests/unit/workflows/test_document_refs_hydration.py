"""workflows.source-node-hydrates-lazily (#4390), the two cases 72e7efc1d2 broke: a library path with no library leaves the references as
they are (15 workflow tests went red on `Library does not exist`), and a segment's work unit is never slimmed to a page reference (a
line, word or sign read landed nowhere)."""
from __future__ import annotations

from fichero_server.workflows import document_refs
from fichero_server.workflows.selection import SEGMENT_TARGET_KEY


def test_references_stay_when_the_library_path_has_no_library(tmp_path):
    refs = [{"id": "doc-1", "name": "p1", "doc_type": "page", "parent_id": None, "sequence": 1, "path": "p1.png"}]
    assert document_refs.hydrate_documents(refs, str(tmp_path / "no-library.fichero")) == refs


def test_a_segments_work_unit_is_kept_whole_and_a_page_is_slimmed():
    page = {"id": "doc-1", "name": "p1", "doc_type": "page", "parent_id": None, "sequence": 1, "path": "p1.png",
            "page_content": "the whole page", "metadata": {"a": 1}}
    segment = {**page, "page_content": "vecino de la ciudad", SEGMENT_TARGET_KEY: {"segment_id": "seg-1", "level": "word", "text": ""}}
    slim_page, kept = document_refs.slim_documents([page, segment])
    assert set(slim_page) == set(document_refs.REF_FIELDS) and "page_content" not in slim_page
    assert kept is segment, "a segment unit stays whole, with its own text and target"
