from __future__ import annotations

from pathlib import Path

from fichero.db import db_manager
from fichero.models import DocType, FileType, Document
from fichero.tinderbox_link_import import import_tinderbox_links


def _write_tbx(path: Path, body: str) -> None:
    path.write_text(
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<tbx>\n" + body + "\n</tbx>\n",
        encoding="utf-8",
    )


def test_import_tinderbox_links_upserts_and_removes_deleted_notes(tmp_path):
    library_path = tmp_path / "tbx.fichero"
    tbx_path = tmp_path / "notes.tbx"

    _write_tbx(
        tbx_path,
        """
<note ID="n1" Name="First" Path="/One" Text="alpha text" Tags="a,b" Modified="2024-01-01" />
<note ID="n2" Name="Second" Path="/Two" Text="beta text" />
        """.strip(),
    )

    summary = import_tinderbox_links(
        library_path=library_path,
        tbx_path=tbx_path,
        reset=False,
    )

    db = db_manager.get_database(library_path)
    roots = [
        d
        for d in db.all(Document)
        if d.doc_type == DocType.folder
        and (d.metadata or {}).get("source_type") == "tinderbox_link_import"
    ]
    assert len(roots) == 1

    docs = [
        d
        for d in db.all(Document)
        if d.parent_id == roots[0].id and d.doc_type == DocType.file
    ]
    assert len(docs) == 2
    by_id = {(d.metadata or {}).get("tinderbox_id"): d for d in docs}
    assert by_id["n1"].file_type == FileType.text
    assert by_id["n1"].page_content == "alpha text"
    assert by_id["n2"].page_content == "beta text"
    assert summary.imported_notes == 2

    _write_tbx(
        tbx_path,
        """
<note ID="n1" Name="First updated" Path="/One" Text="alpha updated" Tags="a,c" Modified="2024-01-02" />
        """.strip(),
    )

    summary2 = import_tinderbox_links(
        library_path=library_path,
        tbx_path=tbx_path,
        reset=False,
    )

    docs_after = [
        d
        for d in db.all(Document)
        if d.parent_id == roots[0].id and d.doc_type == DocType.file
    ]
    assert len(docs_after) == 1
    only = docs_after[0]
    assert (only.metadata or {}).get("tinderbox_id") == "n1"
    assert only.name == "First updated"
    assert only.page_content == "alpha updated"
    assert summary2.updated_notes == 1
    assert summary2.deleted_notes == 1


def test_import_tinderbox_links_skips_url_bookmarks_without_text(tmp_path):
    library_path = tmp_path / "tbx-url.fichero"
    tbx_path = tmp_path / "bookmarks.tbx"
    _write_tbx(
        tbx_path,
        """
<note ID="n-url" Name="Bookmark" URL="https://example.com" Text="" />
<note ID="n-text" Name="Real" Text="content" />
        """.strip(),
    )

    summary = import_tinderbox_links(library_path=library_path, tbx_path=tbx_path)
    db = db_manager.get_database(library_path)
    note_docs = [
        d
        for d in db.all(Document)
        if d.doc_type == DocType.file
        and (d.metadata or {}).get("source_type") == "tinderbox_note"
    ]
    assert len(note_docs) == 1
    assert note_docs[0].name == "Real"
    assert summary.skipped_notes >= 1
