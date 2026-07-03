from __future__ import annotations

import zipfile
from pathlib import Path

from typer.testing import CliRunner

from fichero import __main__ as cli
from fichero.importers.sergio_import import SergioImportSummary, import_sergio_corpus_via_http


runner = CliRunner()
_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


def _build_xlsx(rows: list[list[str | int | None]]) -> bytes:
    shared: list[str] = []
    shared_index: dict[str, int] = {}

    def s_idx(value: str) -> int:
        if value not in shared_index:
            shared_index[value] = len(shared)
            shared.append(value)
        return shared_index[value]

    row_xml = []
    for r_i, row in enumerate(rows, start=1):
        cells = []
        for c_i, value in enumerate(row, start=1):
            if value is None:
                continue
            col = ""
            n = c_i
            while n:
                n, rem = divmod(n - 1, 26)
                col = chr(ord("A") + rem) + col
            ref = f"{col}{r_i}"
            cells.append(f'<c r="{ref}" t="s"><v>{s_idx(str(value))}</v></c>')
        row_xml.append(f"<row>{''.join(cells)}</row>")

    sheet_xml = (
        f'<worksheet xmlns="{_NS}"><sheetData>{"".join(row_xml)}</sheetData></worksheet>'
    )
    shared_xml = (
        f'<sst xmlns="{_NS}" count="{len(shared)}" uniqueCount="{len(shared)}">'
        + "".join(f"<si><t>{v}</t></si>" for v in shared)
        + "</sst>"
    )
    workbook_xml = (
        f'<workbook xmlns="{_NS}"><sheets><sheet name="Sheet1" sheetId="1" r:id="rId1" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"/>'
        "</sheets></workbook>"
    )

    from io import BytesIO

    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "[Content_Types].xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
<Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>
</Types>""",
        )
        zf.writestr(
            "_rels/.rels",
            """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>""",
        )
        zf.writestr(
            "xl/_rels/workbook.xml.rels",
            """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" Target="sharedStrings.xml"/>
</Relationships>""",
        )
        zf.writestr("xl/workbook.xml", workbook_xml)
        zf.writestr("xl/worksheets/sheet1.xml", sheet_xml)
        zf.writestr("xl/sharedStrings.xml", shared_xml)
    return buf.getvalue()


class FakeDoc:
    def __init__(self, doc_id: str, path: str):
        self.id = doc_id
        self.path = path


class FakeClient:
    def __init__(self) -> None:
        self.created_library: str | None = None
        self.docs: dict[str, list[FakeDoc]] = {}
        self.created_docs: list[dict] = []
        self.imported_files: list[tuple[Path, str | None]] = []
        self.next_id = 0

    def create_library(self, path: str) -> None:
        self.created_library = path

    def list_documents(self, *, parent_id: str | None = None, **_kwargs) -> list[FakeDoc]:
        return list(self.docs.get(parent_id or "", []))

    def create_document(self, **payload):
        self.next_id += 1
        doc_id = f"doc-{self.next_id}"
        doc = FakeDoc(doc_id, payload["path"])
        self.docs.setdefault(payload.get("parent_id") or "", []).append(doc)
        self.created_docs.append({"id": doc_id, **payload})
        return doc

    def request(self, method: str, path: str, *, json=None, **_kwargs):
        if method == "POST" and path == "/api/documents":
            doc = self.create_document(**json)
            return {"id": doc.id, **json}
        if method == "PUT" and path.startswith("/api/documents/"):
            doc_id = path.rsplit("/", 1)[-1]
            self.created_docs.append({"id": doc_id, **json})
            return {"id": doc_id, **json}
        raise AssertionError(f"unexpected request: {method} {path}")

    def import_file(self, path: Path, parent_id: str | None = None):
        self.next_id += 1
        doc = FakeDoc(f"file-{self.next_id}", str(path))
        self.docs.setdefault(parent_id or "", []).append(doc)
        self.imported_files.append((path, parent_id))
        return doc


def test_import_sergio_corpus_via_http_routes_files_and_rows(tmp_path):
    source_root = tmp_path / "notebooks"
    source_root.mkdir()
    (source_root / "IMG_0001.jpg").write_bytes(b"fake-jpg-1")
    (source_root / "IMG_0002.jpg").write_bytes(b"fake-jpg-2")
    (source_root / "ignore.bin").write_bytes(b"skip")

    spreadsheet = tmp_path / "catalogue.xlsx"
    spreadsheet.write_bytes(
        _build_xlsx(
            [
                ["filename", "title"],
                ["IMG_0001.jpg", "Matched row"],
                ["MISSING.jpg", "Unmatched row"],
            ]
        )
    )

    client = FakeClient()
    summary = import_sergio_corpus_via_http(
        client,
        library_path=tmp_path / "Sergio.fichero",
        source_root=source_root,
        spreadsheet_path=spreadsheet,
        auto_embed=False,
    )

    assert summary.imported_files == 2
    assert summary.spreadsheet_rows == 2
    assert summary.matched_rows == 1
    assert summary.unmatched_rows == 1
    assert summary.skipped_files == 1
    assert client.created_library == str((tmp_path / "Sergio.fichero").resolve())
    assert [path.name for path, _parent_id in client.imported_files] == [
        "IMG_0001.jpg",
        "IMG_0002.jpg",
    ]
    assert any(
        doc["path"] == f"xlsx://{spreadsheet.name}#row=2"
        and doc["metadata"]["matched_document_id"] == "file-4"
        for doc in client.created_docs
    )


def test_cli_import_sergio_corpus_invokes_http_importer(monkeypatch, tmp_path):
    calls: list[dict] = []

    def fake_import_sergio_corpus_via_http(client, **kwargs):
        calls.append({"client": client, **kwargs})
        return SergioImportSummary(
            library_path=kwargs["library_path"],
            root_document_id="root-1",
            imported_files=2,
            spreadsheet_rows=3,
            matched_rows=2,
            unmatched_rows=1,
            skipped_files=4,
            errors=[],
        )

    monkeypatch.setattr(
        "fichero.importers.sergio_import.import_sergio_corpus_via_http",
        fake_import_sergio_corpus_via_http,
    )

    result = runner.invoke(
        cli.app,
        [
            "--base-url",
            "http://remote-engine.test",
            "import-sergio-corpus",
            "--library-path",
            str(tmp_path / "Sergio.fichero"),
            "--source-root",
            str(tmp_path / "notebooks"),
            "--spreadsheet-path",
            str(tmp_path / "catalogue.xlsx"),
            "--reset",
        ],
    )

    assert result.exit_code == 0
    assert calls[0]["reset"] is True
    assert calls[0]["client"].base_url == "http://remote-engine.test"
    assert "imported_files: 2" in result.output
    assert "unmatched_rows: 1" in result.output
