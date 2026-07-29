"""Backend coverage for previously untested symbols in `fichero/bibliography`."""

from __future__ import annotations

import sys
import types

from fichero_server.bibliography.extractor import extract_from_pdf_metadata
from fichero_server.bibliography import importers


def test_extract_from_pdf_metadata_non_pdf_or_missing_path_returns_empty(tmp_path):
    non_pdf = tmp_path / "notes.txt"
    non_pdf.write_text("hello")
    assert extract_from_pdf_metadata(non_pdf) == {}

    missing = tmp_path / "missing.pdf"
    assert extract_from_pdf_metadata(missing) == {}


def test_extract_from_pdf_metadata_parses_fitz_metadata_and_authors(tmp_path, monkeypatch):
    path = tmp_path / "paper.pdf"
    path.write_bytes(b"%PDF-1.4")

    fake_doc = types.SimpleNamespace(
        metadata={
            "title": "  Sample Title ",
            "author": "Alice;Bob, Carl",
            "subject": "A historical dataset",
            "keywords": " history, archive ",
            "creationDate": "D:2021-03-01",
        }
    )

    fake_fitz = types.ModuleType("fitz")
    fake_fitz.open = lambda _path: fake_doc
    fake_doc.close = lambda: None

    monkeypatch.setitem(sys.modules, "fitz", fake_fitz)

    extracted = extract_from_pdf_metadata(path)

    assert extracted["title"] == "Sample Title"
    assert extracted["authors"] == ["Alice", "Bob", "Carl"]
    assert extracted["metadata"]["pdf_subject"] == "A historical dataset"
    assert extracted["metadata"]["pdf_keywords"] == "history, archive"
    assert extracted["date"] == "2021"


def _bibtex_payload(title: str, author: str, year: str) -> str:
    return (
        "@book{entry,\n"
        f"  title={{{title}}},\n"
        f"  author={{{author}}},\n"
        f"  year={{{year}}}\n"
        "}\n"
    )


def test_read_file_parses_sidecar_by_extension(tmp_path):
    bib = tmp_path / "paper.bib"
    bib.write_text(_bibtex_payload("Shifting Livelihoods", "Tubb, Daniel", "2020"))

    entries = importers.read_file(bib)

    assert len(entries) == 1
    assert entries[0]["title"] == "Shifting Livelihoods"


def test_read_sidecar_prefers_filename_match(tmp_path):
    doc = tmp_path / "paper.pdf"
    doc.write_bytes(b"%PDF-1.4")
    (tmp_path / "paper.bib").write_text(
        _bibtex_payload("Source Match", "Tubb, Daniel", "2020")
    )

    sidecars = importers.read_sidecar(doc)
    assert sidecars
    assert sidecars[0]["title"] == "Source Match"


def test_read_folder_sidecars_prefers_reference_catalog(tmp_path):
    doc = tmp_path / "paper.pdf"
    doc.write_bytes(b"%PDF-1.4")
    (tmp_path / "references.bib").write_text(
        _bibtex_payload("Folder Match", "Tubb, Daniel", "2020")
    )
    (tmp_path / "library.bib").write_text(
        _bibtex_payload("Should Not Be Used", "Someone", "1999")
    )

    sidecars = importers.read_folder_sidecars(doc)
    assert sidecars
    assert sidecars[0]["title"] == "Folder Match"


def test_read_sidecar_and_folder_sidecars_return_empty_when_missing(tmp_path):
    doc = tmp_path / "notes.txt"
    doc.write_text("text")

    assert importers.read_sidecar(doc) == []
    assert importers.read_folder_sidecars(doc) == []
