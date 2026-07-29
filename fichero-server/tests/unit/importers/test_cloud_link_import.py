from __future__ import annotations

import json

from typer.testing import CliRunner

from fichero_cli import __main__ as cli
from fichero_server.importers.cloud_link_import import (
    import_box_links_via_http,
    import_dropbox_links_via_http,
)


runner = CliRunner()


class FakeDoc:
    def __init__(self, doc_id: str, path: str, doc_type: str = "folder") -> None:
        self.id = doc_id
        self.path = path
        self.doc_type = doc_type


class FakeClient:
    def __init__(self) -> None:
        self.created_library: str | None = None
        self.docs: dict[str, list[FakeDoc]] = {}
        self.next_id = 0

    def create_library(self, path: str) -> None:
        self.created_library = path

    def list_documents(self, *, parent_id: str | None = None, **_kwargs) -> list[FakeDoc]:
        return list(self.docs.get(parent_id or "", []))

    def request(self, method: str, path: str, *, json=None, **_kwargs):
        if method == "POST" and path == "/api/documents":
            self.next_id += 1
            doc = FakeDoc(f"doc-{self.next_id}", json["path"], json["doc_type"])
            self.docs.setdefault(json.get("parent_id") or "", []).append(doc)
            return {"id": doc.id, **json}
        if method == "PUT" and path.startswith("/api/documents/"):
            doc_id = path.rsplit("/", 1)[-1]
            return {"id": doc_id, **json}
        raise AssertionError(f"unexpected request: {method} {path}")


def test_cli_import_dropbox_links_invokes_importer(monkeypatch, tmp_path):
    calls: list[dict] = []

    def fake_import_dropbox_links(client, **kwargs):
        from fichero_server.importers.cloud_link_import import CloudLinkImportSummary

        calls.append({"client": client, **kwargs})
        return CloudLinkImportSummary(
            provider="dropbox",
            library_path=kwargs["library_path"],
            root_document_id="root-1",
            imported_links=3,
            skipped_rows=1,
            errors=[],
        )

    monkeypatch.setattr(
        "fichero_server.importers.cloud_link_import.import_dropbox_links_via_http",
        fake_import_dropbox_links,
    )

    result = runner.invoke(
        cli.app,
        [
            "--base-url",
            "http://remote-engine.test",
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
    assert calls[0]["client"].base_url == "http://remote-engine.test"
    assert "imported_links: 3" in result.output


def test_import_dropbox_links_via_http_creates_reference_documents(tmp_path):
    library = tmp_path / "DropboxLinks.fichero"
    manifest = tmp_path / "dropbox_links.json"
    manifest.write_text(
        json.dumps(
            [
                {
                    "name": "Letter 001",
                    "url": "https://www.dropbox.com/scl/fi/a1/letter001.jpg?dl=0",
                    "external_id": "dbx-1",
                },
                {
                    "name": "Skip me",
                    "url": "https://example.com/not-dropbox",
                },
            ]
        ),
        encoding="utf-8",
    )

    client = FakeClient()
    summary = import_dropbox_links_via_http(
        client,
        library_path=library,
        manifest_path=manifest,
        reset=True,
    )

    assert summary.imported_links == 1
    assert summary.skipped_rows == 1
    assert summary.errors == []
    assert client.created_library == str(library.resolve())


def test_cli_import_box_links_invokes_importer(monkeypatch, tmp_path):
    calls: list[dict] = []

    def fake_import_box_links(client, **kwargs):
        from fichero_server.importers.cloud_link_import import CloudLinkImportSummary

        calls.append({"client": client, **kwargs})
        return CloudLinkImportSummary(
            provider="box",
            library_path=kwargs["library_path"],
            root_document_id="root-1",
            imported_links=2,
            skipped_rows=2,
            errors=[],
        )

    monkeypatch.setattr(
        "fichero_server.importers.cloud_link_import.import_box_links_via_http",
        fake_import_box_links,
    )

    result = runner.invoke(
        cli.app,
        [
            "--base-url",
            "http://remote-engine.test",
            "import-box-links",
            "--library-path",
            str(tmp_path / "BoxLinks.fichero"),
            "--manifest-path",
            str(tmp_path / "box_links.json"),
            "--reset",
        ],
    )

    assert result.exit_code == 0
    assert calls[0]["reset"] is True
    assert calls[0]["client"].base_url == "http://remote-engine.test"
    assert "imported_links: 2" in result.output


def test_import_box_links_via_http_creates_reference_documents(tmp_path):
    library = tmp_path / "BoxLinks.fichero"
    manifest = tmp_path / "box_links.json"
    manifest.write_text(
        json.dumps(
            [
                {
                    "name": "Box Letter 001",
                    "url": "https://app.box.com/file/12345",
                    "external_id": "box-1",
                },
                {
                    "name": "Skip me",
                    "url": "https://example.com/not-box",
                },
            ]
        ),
        encoding="utf-8",
    )

    client = FakeClient()
    summary = import_box_links_via_http(
        client,
        library_path=library,
        manifest_path=manifest,
        reset=True,
    )

    assert summary.imported_links == 1
    assert summary.skipped_rows == 1
    assert summary.errors == []
    assert client.created_library == str(library.resolve())
