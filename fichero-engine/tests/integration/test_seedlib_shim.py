"""The shared seeder shim builds a library and reports derived ground truth."""


def test_seed_builds_library_with_derived_counts(tmp_path):
    from tests.integration._seedlib import seed

    summary = seed(tmp_path / "shim.fichero")

    # Counts are derived by querying the library back (never hand-declared).
    # documents_total = 4 explicit documents (collection, letter, photo, page)
    # + 1 mirrored Document node for the seeded workflow (#11 Phase 1 —
    # saving a Workflow mirrors it into the document tree for sidebar
    # placement; see `_save_workflow_document` in fichero/db.py).
    assert summary["expected"]["documents_total"] == 6
    assert summary["expected"]["children_of_collection"] == 2
    assert summary["expected"]["entities"] == 3
    assert summary["expected"]["claims"] == 3
    assert summary["expected"]["workflows"] == 1
    assert summary["expected"]["artifacts_for_letter"] == 1
    # Seeded IDs are exposed by name.
    assert summary["keys"]["collection"] == "test-collection"
    assert summary["keys"]["doc_letter"] == "test-doc-letter"
