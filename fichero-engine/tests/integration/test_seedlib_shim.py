"""The shared seeder shim builds a library and reports derived ground truth."""


def test_seed_builds_library_with_derived_counts(tmp_path):
    from tests.integration._seedlib import seed

    summary = seed(tmp_path / "shim.fichero")

    # Counts are derived by querying the library back (never hand-declared).
    assert summary["expected"]["documents_total"] == 5
    assert summary["expected"]["children_of_collection"] == 2
    assert summary["expected"]["entities"] == 3
    assert summary["expected"]["claims"] == 3
    assert summary["expected"]["workflows"] == 1
    assert summary["expected"]["artifacts_for_letter"] == 1
    # Seeded IDs are exposed by name.
    assert summary["keys"]["collection"] == "test-collection"
    assert summary["keys"]["doc_letter"] == "test-doc-letter"
