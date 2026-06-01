from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from fichero import __main__ as cli
from fichero.cloud_link_import import import_dropbox_links
from fichero.db import db_manager
from fichero.models import DocType, Document


runner = CliRunner()


def test_import_dropbox_links_creates_reference_documents(tmp_path):
    library = tmp_path / "DropboxLinks.fichero"
    manifest = tmp_path / "dropbox_links.json"
    manifest.write_text(
        json.dumps(
            [
                {
                    "name": "Letter 001",
                    "url": "https://www.dropbox.com/scl/fi/a1/letter001.jpg?dl=0",
                    "external_id": "dbx-1",
                    "path_display": "/Sergio/letter001.jpg",
                },
                {
                    "name": "Letter 002",
                    "url": "https://www.dropbox.com/scl/fi/a2/letter002.pdf?dl=0",
                    "external_id": "dbx-2",
                    "path_display": "/Sergio/letter002.pdf",
                },
            ]
        ),
        encoding="utf-8",
    )

    try:
        summary = import_dropbox_links(
            library_path=library,
            manifest_path=manifest,
            reset=True,
        )
        docs = db_manager.get_database(library).query(Document)
    finally:
        db_manager.close_all()

    assert summary.imported_links == 2
    assert summary.skipped_rows == 0
    assert summary.errors == []
    assert any(d.name == "Dropbox Linked Sources" and d.doc_type == DocType.folder for d in docs)
    link_docs = [d for d in docs if d.metadata and d.metadata.get("source_type") == "dropbox_link"]
    assert len(link_docs) == 2
    assert all(d.path.startswith("https://www.dropbox.com/") for d in link_docs)


def test_cli_import_dropbox_links_invokes_importer(monkeypatch, tmp_path):
    calls: list[dict] = []

    def fake_import_dropbox_links(**kwargs):
        from fichero.cloud_link_import import CloudLinkImportSummary

        calls.append(kwargs)
        return CloudLinkImportSummary(
            provider="dropbox",
            library_path=kwargs["library_path"],
            root_document_id="root-1",
            imported_links=3,
            skipped_rows=1,
            errors=[],
        )

    monkeypatch.setattr(
        "fichero.cloud_link_import.import_dropbox_links",
        fake_import_dropbox_links,
    )

    result = runner.invoke(
        cli.app,
        [
            "import-dropbox-links",
            "--library-path",
            str(tmp_path / "DropboxLinks.fichero"),
            "--manifest-path",
            str(tmp_path / "dropbox_links.json"),
            "--reset",
        ],
    )

    assert result.exit_code == 0
    assert calls[0]["reset"] is True
    assert "imported_links: 3" in result.output
