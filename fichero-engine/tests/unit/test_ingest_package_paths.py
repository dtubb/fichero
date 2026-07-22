"""Regression tests for package-relative ingest paths."""

from pathlib import Path


def test_copy_into_package_stores_library_relative_path(tmp_path):
    """COPY mode should not bake the .fichero package name into doc.path."""
    from fichero.importers.ingest import IngestMode, ingest_file

    source = tmp_path / "source.jpg"
    source.write_bytes(b"fake image bytes")
    package = tmp_path / "Marshall.fichero"

    doc = ingest_file(
        source,
        mode=IngestMode.COPY,
        save=False,
        package_path=package,
        extract_metadata=False,
        extract_text=False,
    )

    assert doc.path is not None
    assert doc.path.startswith("files/")
    assert not Path(doc.path).is_absolute()
    assert not doc.path.startswith(str(package))
    assert (package / doc.path).exists()
