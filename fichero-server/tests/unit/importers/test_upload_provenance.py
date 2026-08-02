"""#4471 part 3: an upload's temp name must never become provenance.

The source name is provenance in an archival tool — a document recorded as
``fichero_upload_<random>.pdf`` has lost the fact connecting it to the
physical original, and nobody can cite a tempfile. ``original_filename``
rides INTO ``ingest_file`` (not a post-hoc rename): the display name is
right BEFORE page children are named, and the server temp path is never
recorded as source_path/source_folder.
"""

from pathlib import Path

from fichero_server.importers.ingest import IngestMode, ingest_file


def _upload_temp(tmp_path: Path, name: str = "fichero_upload_ab12cd.jpg") -> Path:
    temp = tmp_path / name
    temp.write_bytes(b"fake image bytes")
    return temp


def test_original_filename_is_the_document_name(tmp_path):
    doc = ingest_file(
        _upload_temp(tmp_path),
        mode=IngestMode.COPY,
        save=False,
        package_path=tmp_path / "Lib.fichero",
        extract_metadata=False,
        extract_text=False,
        original_filename="Diario 1893 - abril.jpg",
    )
    assert doc.name == "Diario 1893 - abril.jpg"
    assert "fichero_upload" not in doc.name


def test_temp_path_is_not_recorded_as_source(tmp_path):
    doc = ingest_file(
        _upload_temp(tmp_path),
        mode=IngestMode.COPY,
        save=False,
        package_path=tmp_path / "Lib.fichero",
        extract_metadata=False,
        extract_text=False,
        original_filename="Diario 1893 - abril.jpg",
    )
    assert doc.metadata.get("source_filename") == "Diario 1893 - abril.jpg"
    for key in ("source_path", "source_folder", "source_mtime"):
        assert key not in doc.metadata, (
            f"{key} would record the server temp dir — a lie about origin, "
            "not provenance"
        )


def test_path_based_ingest_keeps_real_source_path(tmp_path):
    """No original_filename (the path IS the source, e.g. folder ingest):
    behaviour unchanged — real path recorded, name from the file."""
    real = tmp_path / "Diario 1893 - mayo.jpg"
    real.write_bytes(b"fake image bytes")
    doc = ingest_file(
        real,
        mode=IngestMode.COPY,
        save=False,
        package_path=tmp_path / "Lib.fichero",
        extract_metadata=False,
        extract_text=False,
    )
    assert doc.name == "Diario 1893 - mayo.jpg"
    assert doc.metadata.get("source_path") == str(real)
    assert "source_filename" not in doc.metadata


def test_pdf_pages_inherit_the_real_name(tmp_path):
    """The live defect (#4465 round trip): pages listed as
    'fichero_upload_….pdf - Page N'. Pages are named from parent_doc.name
    during ingest, so the real name must be in place before they exist."""
    import shutil

    from tests.fixture_paths import sample_file

    temp = tmp_path / "fichero_upload_zz99.pdf"
    shutil.copyfile(sample_file("multipage.pdf"), temp)

    from fichero_server.db import Database

    lib = tmp_path / "Lib.fichero"
    lib.mkdir()
    db = Database(lib / "fichero.duckdb")
    try:
        doc = ingest_file(
            temp,
            mode=IngestMode.COPY,
            save=True,
            db=db,
            package_path=lib,
            extract_metadata=False,
            extract_text=True,
            auto_embed=False,
            original_filename="Marshall Diary 1893.pdf",
        )
        from fichero_server.models import Document

        pages = db.query(Document, parent_id=doc.id)
        assert pages, "fixture PDF should split into pages"
        for page in pages:
            assert page.name.startswith("Marshall Diary 1893.pdf - Page"), page.name
            assert "fichero_upload" not in page.name
    finally:
        db.close()
