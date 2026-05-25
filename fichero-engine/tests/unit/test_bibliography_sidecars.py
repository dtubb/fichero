"""Tests for bibliography sidecar ingest support."""

from pathlib import Path
from unittest.mock import patch

from fichero.ingest import ingest_file


@patch("fichero.bookmarks.create_bookmark")
def test_loads_bibliography_sidecar(mock_bookmark, tmp_path: Path) -> None:
    """A sibling bibliography file should populate canonical metadata."""
    file = tmp_path / "paper.pdf"
    file.write_bytes(b"fake pdf bytes")
    (tmp_path / "paper.bib").write_text(
        "@book{paper,\n"
        "  author = {Tubb, Daniel},\n"
        "  title = {Shifting Livelihoods},\n"
        "  year = {2020},\n"
        "  publisher = {Duke University Press},\n"
        "}\n",
        encoding="utf-8",
    )

    mock_bookmark.return_value = None

    doc = ingest_file(file, extract_metadata=False, extract_text=False, save=False)

    assert doc.source_metadata is not None
    assert doc.source_metadata["title"] == "Shifting Livelihoods"
    assert doc.bibtex is not None
    assert "@book{" in doc.bibtex
