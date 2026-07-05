"""Unit tests for xlsx_reader — XLSX → structured records (#1237)."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from fichero.loaders import xlsx_reader
from fichero.loaders.xlsx_reader import (
    _col_index,
    _index_to_col_letter,
    _parse_cell_ref,
    read_xlsx_records,
)


# ---------------------------------------------------------------------------
# Helper: build a minimal valid .xlsx in memory
# ---------------------------------------------------------------------------

_CONTENT_TYPES = """\
<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml"
    ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml"
    ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/sharedStrings.xml"
    ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>
</Types>
"""

_WORKBOOK = """\
<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheets>
    <sheet name="Sheet1" sheetId="1" r:id="rId1"
      xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"/>
  </sheets>
</workbook>
"""

_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


def _make_shared_strings(strings: list[str]) -> str:
    items = "\n".join(f"  <si><t>{s}</t></si>" for s in strings)
    return f"""\
<?xml version="1.0" encoding="UTF-8"?>
<sst xmlns="{_NS}" count="{len(strings)}" uniqueCount="{len(strings)}">
{items}
</sst>
"""


def _make_sheet(rows: list[list[str | int | None]]) -> str:
    """Build a worksheet XML where strings are inlined as shared-string refs."""
    # Collect unique strings to build shared strings index
    seen: list[str] = []

    def _ss_idx(val: str) -> int:
        if val not in seen:
            seen.append(val)
        return seen.index(val)

    # Pre-scan to build the shared-strings list
    for row in rows:
        for cell in row:
            if isinstance(cell, str):
                _ss_idx(cell)

    row_xmls: list[str] = []
    for r_idx, row in enumerate(rows, start=1):
        cells: list[str] = []
        for c_idx, cell in enumerate(row):
            col_letter = chr(ord("A") + c_idx)
            ref = f"{col_letter}{r_idx}"
            if isinstance(cell, str):
                idx = _ss_idx(cell)
                cells.append(f'<c r="{ref}" t="s"><v>{idx}</v></c>')
            elif isinstance(cell, (int, float)):
                cells.append(f'<c r="{ref}"><v>{cell}</v></c>')
            # None → omit (sparse)
        if cells:
            row_xmls.append(f'  <row r="{r_idx}">{"".join(cells)}</row>')

    return (
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<worksheet xmlns="{_NS}"><sheetData>'
        + "\n".join(row_xmls)
        + "</sheetData></worksheet>"
    ), seen  # return (xml, shared_strings_list)


def _build_xlsx(rows: list[list[str | int | None]]) -> bytes:
    """Return a bytes buffer containing a valid .xlsx for the given rows."""
    sheet_xml, shared = _make_sheet(rows)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", _CONTENT_TYPES)
        zf.writestr("xl/workbook.xml", _WORKBOOK)
        zf.writestr("xl/sharedStrings.xml", _make_shared_strings(shared))
        zf.writestr("xl/worksheets/sheet1.xml", sheet_xml)
    return buf.getvalue()


def _xlsx_fixture(tmp_path: Path, rows: list[list]) -> Path:
    p = tmp_path / "test.xlsx"
    p.write_bytes(_build_xlsx(rows))
    return p


def _malicious_xlsx_fixture(tmp_path: Path) -> Path:
    p = tmp_path / "evil.xlsx"
    malicious_shared_strings = """\
<?xml version="1.0"?>
<!DOCTYPE lolz [
 <!ENTITY lol "lol">
 <!ENTITY lol1 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
]>
<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <si><t>&lol1;</t></si>
</sst>
"""
    sheet_xml = (
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<worksheet xmlns="{_NS}"><sheetData>'
        '<row r="1"><c r="A1" t="s"><v>0</v></c></row>'
        "</sheetData></worksheet>"
    )
    with zipfile.ZipFile(p, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", _CONTENT_TYPES)
        zf.writestr("xl/workbook.xml", _WORKBOOK)
        zf.writestr("xl/sharedStrings.xml", malicious_shared_strings)
        zf.writestr("xl/worksheets/sheet1.xml", sheet_xml)
    return p


# ---------------------------------------------------------------------------
# Unit tests — helpers
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_col_index_a(self):
        assert _col_index("A") == 0

    def test_col_index_z(self):
        assert _col_index("Z") == 25

    def test_col_index_aa(self):
        assert _col_index("AA") == 26


def test_xlsx_rejects_billion_laughs_entities(tmp_path):
    path = _malicious_xlsx_fixture(tmp_path)

    with pytest.raises(ValueError, match="entity declarations"):
        read_xlsx_records(path)


def test_xlsx_rejects_oversized_zip_member(tmp_path):
    path = tmp_path / "oversized.xlsx"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as zf:
        zf.writestr("[Content_Types].xml", _CONTENT_TYPES)
        zf.writestr("xl/workbook.xml", _WORKBOOK)
        zf.writestr("xl/worksheets/sheet1.xml", "x" * (20 * 1024 * 1024 + 1))

    with pytest.raises(ValueError, match="XLSX member too large"):
        read_xlsx_records(path)


def test_xlsx_rejects_member_count_or_total_size_before_xml_parse(tmp_path, monkeypatch):
    path = tmp_path / "many-members.xlsx"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as zf:
        zf.writestr("[Content_Types].xml", _CONTENT_TYPES)
        zf.writestr("xl/workbook.xml", _WORKBOOK)
        zf.writestr("xl/sharedStrings.xml", _make_shared_strings(["header"]))
        zf.writestr("xl/worksheets/sheet1.xml", _make_sheet([["Header"], ["Value"]])[0])
        zf.writestr("xl/extra1.xml", "A" * 80)
        zf.writestr("xl/extra2.xml", "B" * 80)

    monkeypatch.setattr(xlsx_reader, "_MAX_XLSX_MEMBER_COUNT", 5)
    monkeypatch.setattr(xlsx_reader, "_MAX_XLSX_TOTAL_UNCOMPRESSED", 200)
    monkeypatch.setattr(
        xlsx_reader,
        "parse_xml",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("parse_xml should not run")),
    )

    with pytest.raises(ValueError, match="too many members|total uncompressed size too large"):
        read_xlsx_records(path)

    def test_col_index_ab(self):
        assert _col_index("AB") == 27

    def test_index_to_col_letter_roundtrip(self):
        for i in range(50):
            assert _col_index(_index_to_col_letter(i)) == i

    def test_parse_cell_ref_a1(self):
        assert _parse_cell_ref("A1") == (0, 0)

    def test_parse_cell_ref_c3(self):
        assert _parse_cell_ref("C3") == (2, 2)

    def test_parse_cell_ref_invalid(self):
        with pytest.raises(ValueError):
            _parse_cell_ref("1A")


# ---------------------------------------------------------------------------
# Unit tests — read_xlsx_records
# ---------------------------------------------------------------------------


class TestReadXlsxRecords:
    def test_basic_three_column(self, tmp_path):
        path = _xlsx_fixture(tmp_path, [
            ["Name", "Date", "Amount"],
            ["Alice", "1842-01-01", "100"],
            ["Bob",   "1843-06-15", "200"],
        ])
        records = read_xlsx_records(path)
        assert len(records) == 2
        assert records[0] == {"Name": "Alice", "Date": "1842-01-01", "Amount": "100"}
        assert records[1] == {"Name": "Bob",   "Date": "1843-06-15", "Amount": "200"}

    def test_column_map_by_header_name(self, tmp_path):
        path = _xlsx_fixture(tmp_path, [
            ["Nombre", "Fecha", "Lugar"],
            ["García", "1820", "Quibdó"],
        ])
        records = read_xlsx_records(path, column_map={"Nombre": "name", "Fecha": "year"})
        assert records[0]["name"] == "García"
        assert records[0]["year"] == "1820"
        assert records[0]["_unmapped"] == {"Lugar": "Quibdó"}

    def test_column_map_by_letter(self, tmp_path):
        path = _xlsx_fixture(tmp_path, [
            ["X", "Y"],
            ["hello", "world"],
        ])
        records = read_xlsx_records(path, column_map={"A": "first", "B": "second"})
        assert records[0] == {"first": "hello", "second": "world"}

    def test_unmapped_collected(self, tmp_path):
        path = _xlsx_fixture(tmp_path, [
            ["Title", "Notes", "Tags"],
            ["Doc1", "some notes", "a,b"],
        ])
        records = read_xlsx_records(path, column_map={"Title": "name"})
        assert records[0]["name"] == "Doc1"
        assert "_unmapped" in records[0]
        assert records[0]["_unmapped"]["Notes"] == "some notes"
        assert records[0]["_unmapped"]["Tags"] == "a,b"

    def test_no_column_map_passes_headers_through(self, tmp_path):
        path = _xlsx_fixture(tmp_path, [
            ["A", "B"],
            ["1", "2"],
        ])
        records = read_xlsx_records(path)
        assert records[0] == {"A": "1", "B": "2"}
        assert "_unmapped" not in records[0]

    def test_empty_rows_skipped(self, tmp_path):
        path = _xlsx_fixture(tmp_path, [
            ["Name", "Value"],
            ["Alice", "1"],
            [None, None],
            ["Bob", "2"],
        ])
        records = read_xlsx_records(path)
        assert len(records) == 2

    def test_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            read_xlsx_records(tmp_path / "nonexistent.xlsx")

    def test_sheet_index_out_of_range(self, tmp_path):
        path = _xlsx_fixture(tmp_path, [["H"], ["v"]])
        with pytest.raises(ValueError, match="sheet_index"):
            read_xlsx_records(path, sheet_index=5)

    def test_numeric_values(self, tmp_path):
        path = _xlsx_fixture(tmp_path, [
            ["ID", "Count"],
            ["rec1", 42],
        ])
        records = read_xlsx_records(path)
        assert records[0]["Count"] == "42"

    def test_no_data_rows_returns_empty(self, tmp_path):
        path = _xlsx_fixture(tmp_path, [
            ["Header1", "Header2"],
        ])
        records = read_xlsx_records(path)
        assert records == []

    def test_sparse_row_middle_column_empty(self, tmp_path):
        # Row has a value in A and C but not B (cell B is omitted in XML)
        path = _xlsx_fixture(tmp_path, [
            ["A", "B", "C"],
            ["x", None, "z"],
        ])
        records = read_xlsx_records(path)
        assert records[0]["A"] == "x"
        assert "B" not in records[0]  # None cells are skipped
        assert records[0]["C"] == "z"
