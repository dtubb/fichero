

def test_excluded_documents_never_become_work_units(db, test_package):
    # Curation is a promise (user, live 2026-08-20): a doc excluded from
    # processing is skipped whether selected directly or reached by folder
    # expansion, and an all-excluded selection fails loudly.
    import pytest
    from fichero_server.models import DocType, Document
    from fichero_server.workflows.tools.sources import _resolve_selection_pairs

    folder = Document(name="F", doc_type=DocType.folder)
    db.save(folder)
    src = test_package / "a.txt"; src.write_text("hi")
    kept = Document(name="kept", parent_id=folder.id, path="a.txt", page_content="x")
    excluded = Document(
        name="excluded", parent_id=folder.id, path="a.txt",
        page_content="y", exclude_from_processing=True,
    )
    db.save(kept); db.save(excluded)

    pairs = _resolve_selection_pairs(db, [folder.id], str(test_package))
    assert [d.name for _, d in pairs] == ["kept"]

    with pytest.raises(ValueError, match="excluded from processing"):
        _resolve_selection_pairs(db, [excluded.id], str(test_package))
