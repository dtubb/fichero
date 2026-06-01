from __future__ import annotations

import zipfile
from pathlib import Path

from typer.testing import CliRunner

from fichero import __main__ as cli
from fichero.db import db_manager
from fichero.models import DocType, Document
from fichero.sergio_import import import_sergio_corpus


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
            sval = str(value)
            cells.append(f'<c r="{ref}" t="s"><v>{s_idx(sval)}</v></c>')
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


def test_import_sergio_corpus_imports_files_and_spreadsheet_rows(tmp_path, monkeypatch):
    source_root = tmp_path / "notebooks"
    source_root.mkdir()
    (source_root / "IMG_0001.jpg").write_bytes(b"fake-jpg-1")
    (source_root / "IMG_0002.jpg").write_bytes(b"fake-jpg-2")

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
    library = tmp_path / "Sergio.fichero"

    def fake_ingest_file(path, **kwargs):
        db = kwargs["db"]
        doc = Document(
            name=Path(path).name,
            path=str(path),
            doc_type=DocType.file,
            parent_id=kwargs["parent_id"],
            page_content="imported",
        )
        db.save(doc, auto_embed=False)
        return doc

    monkeypatch.setattr("fichero.sergio_import.ingest_file", fake_ingest_file)

    try:
        summary = import_sergio_corpus(
            library_path=library,
            source_root=source_root,
            spreadsheet_path=spreadsheet,
            auto_embed=False,
        )
        docs = db_manager.get_database(library).query(Document)
    finally:
        db_manager.close_all()

    assert summary.imported_files == 2
    assert summary.spreadsheet_rows == 2
    assert summary.matched_rows == 1
    assert summary.unmatched_rows == 1
    assert any(d.name == "Sergio Mosquera Notebooks" for d in docs)
    assert any(d.name == "Spreadsheet Catalogue" and d.doc_type == DocType.folder for d in docs)
    assert any(d.name == "row-2: Matched row" for d in docs)


def test_cli_import_sergio_corpus_invokes_importer(monkeypatch, tmp_path):
    calls: list[dict] = []

    def fake_import_sergio_corpus(**kwargs):
        from fichero.sergio_import import SergioImportSummary

        calls.append(kwargs)
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
        "fichero.sergio_import.import_sergio_corpus",
        fake_import_sergio_corpus,
    )

    result = runner.invoke(
        cli.app,
        [
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
    assert "imported_files: 2" in result.output
    assert "unmatched_rows: 1" in result.output
