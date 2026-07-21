"""
Read .xlsx files as structured records without openpyxl.

Uses stdlib zipfile plus guarded XML parsing to parse the Open XML format directly.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from typing import Any

from fichero.security.xml_security import parse_xml

_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_MAX_XLSX_MEMBER_SIZE = 20 * 1024 * 1024
_MAX_XLSX_TOTAL_UNCOMPRESSED = 100 * 1024 * 1024
_MAX_XLSX_MEMBER_COUNT = 256


def _validate_zip_members(zf: zipfile.ZipFile) -> None:
    infos = zf.infolist()
    if len(infos) > _MAX_XLSX_MEMBER_COUNT:
        raise ValueError(f"XLSX has too many members: {len(infos)}")
    total_uncompressed = 0
    for info in infos:
        if info.file_size > _MAX_XLSX_MEMBER_SIZE:
            raise ValueError(f"XLSX member too large: {info.filename}")
        total_uncompressed += info.file_size
        if total_uncompressed > _MAX_XLSX_TOTAL_UNCOMPRESSED:
            raise ValueError(
                f"XLSX total uncompressed size too large: {total_uncompressed}"
            )


def _parse_xml_member(zf: zipfile.ZipFile, name: str):
    info = zf.getinfo(name)
    if info.file_size > _MAX_XLSX_MEMBER_SIZE:
        raise ValueError(f"XLSX member too large: {name}")
    with zf.open(info) as member:
        return parse_xml(member)


def _col_index(col_str: str) -> int:
    """Convert column letters ('A', 'AB') to 0-based column index."""
    idx = 0
    for ch in col_str.upper():
        idx = idx * 26 + (ord(ch) - ord("A") + 1)
    return idx - 1


def _parse_cell_ref(ref: str) -> tuple[int, int]:
    """Parse 'C3' → (row=2, col=2), both 0-based."""
    m = re.fullmatch(r"([A-Za-z]+)(\d+)", ref)
    if not m:
        raise ValueError(f"Unrecognised cell reference: {ref!r}")
    return int(m.group(2)) - 1, _col_index(m.group(1))


def _read_shared_strings(zf: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in zf.namelist():
        return []
    tree = _parse_xml_member(zf, "xl/sharedStrings.xml")
    result: list[str] = []
    for si in tree.getroot().findall(f"{{{_NS}}}si"):
        # Concatenate all <t> children (handles rich-text runs)
        parts = [t.text or "" for t in si.findall(f".//{{{_NS}}}t")]
        result.append("".join(parts))
    return result


def _sheet_names(zf: zipfile.ZipFile) -> list[str]:
    """Return worksheet XML paths in sheet order (sheet1, sheet2, …)."""
    candidates = [
        n for n in zf.namelist()
        if n.startswith("xl/worksheets/sheet") and n.endswith(".xml")
    ]
    # Natural sort so sheet10 doesn't come before sheet2
    return sorted(
        candidates,
        key=lambda p: int(re.search(r"\d+", p.split("/")[-1]).group()),
    )


def _read_sheet_cells(zf: zipfile.ZipFile, sheet_path: str, shared: list[str]) -> list[list[str | None]]:
    """
    Return a list-of-rows of string values.  Empty cells are None; rows are
    padded to the width of the widest row so every row has the same length.
    """
    tree = _parse_xml_member(zf, sheet_path)
    root = tree.getroot()

    # Collect (row_idx, col_idx, value) triples
    triples: list[tuple[int, int, str | None]] = []
    max_col = 0

    for cell in root.findall(f".//{{{_NS}}}c"):
        ref = cell.get("r")
        if not ref:
            continue
        try:
            r_idx, c_idx = _parse_cell_ref(ref)
        except ValueError:
            continue

        t_attr = cell.get("t", "")
        v_elem = cell.find(f"{{{_NS}}}v")
        is_elem = cell.find(f"{{{_NS}}}is")  # inline string

        value: str | None = None
        if t_attr == "s":
            # Shared string
            if v_elem is not None and v_elem.text is not None:
                try:
                    value = shared[int(v_elem.text)]
                except (IndexError, ValueError):
                    value = ""
        elif t_attr == "inlineStr":
            if is_elem is not None:
                parts = [t.text or "" for t in is_elem.findall(f".//{{{_NS}}}t")]
                value = "".join(parts) or None
        elif t_attr == "b":
            value = "TRUE" if (v_elem is not None and v_elem.text == "1") else "FALSE"
        else:
            if v_elem is not None and v_elem.text is not None:
                value = v_elem.text

        if value is not None:
            triples.append((r_idx, c_idx, value))
            max_col = max(max_col, c_idx)

    if not triples:
        return []

    max_row = max(r for r, _, _ in triples)
    width = max_col + 1

    # Build rectangular grid
    grid: list[list[str | None]] = [[None] * width for _ in range(max_row + 1)]
    for r_idx, c_idx, val in triples:
        grid[r_idx][c_idx] = val

    return grid


def read_xlsx_records(
    path: str | Path,
    *,
    column_map: dict[str, str] | None = None,
    sheet_index: int = 0,
    skip_empty_rows: bool = True,
) -> list[dict[str, Any]]:
    """
    Read an .xlsx file and return one dict per data row.

    The first non-empty row is treated as the header row.  Each subsequent row
    becomes a dict whose keys come from the headers (or from *column_map* when
    supplied).

    Args:
        path: Path to the .xlsx file.
        column_map: Optional mapping from source column identifiers to output
            field names.  Keys may be:
            - The exact header cell text (e.g. ``"Fecha"``).
            - A column letter (e.g. ``"A"``, ``"B"``).
            Columns not present in *column_map* are collected under
            ``"_unmapped"`` on each record.  If *column_map* is ``None``, all
            column headers are used as-is and nothing is unmapped.
        sheet_index: 0-based index of the worksheet to read (default 0 = first
            sheet).
        skip_empty_rows: When True (default), rows where every value is None
            or empty are omitted from the result.

    Returns:
        List of dicts, one per data row.  Each dict may contain an
        ``"_unmapped"`` key holding a sub-dict of columns that had no mapping.

    Raises:
        FileNotFoundError: *path* does not exist.
        ValueError: *sheet_index* is out of range, or the file has no rows.
        zipfile.BadZipFile: *path* is not a valid .xlsx / zip archive.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    with zipfile.ZipFile(path) as zf:
        _validate_zip_members(zf)
        shared = _read_shared_strings(zf)
        sheets = _sheet_names(zf)

        if not sheets:
            raise ValueError(f"No worksheets found in {path.name}")
        if sheet_index >= len(sheets):
            raise ValueError(
                f"sheet_index={sheet_index} is out of range "
                f"(file has {len(sheets)} sheet(s))"
            )

        grid = _read_sheet_cells(zf, sheets[sheet_index], shared)

    if not grid:
        return []

    # First row = headers
    raw_headers = grid[0]
    headers: list[str] = [
        str(h).strip() if h else f"_col{i}"
        for i, h in enumerate(raw_headers)
    ]
    data_rows = grid[1:]

    records: list[dict[str, Any]] = []
    for row in data_rows:
        # Pad short rows
        padded = list(row) + [None] * (len(headers) - len(row))

        if skip_empty_rows and all(v is None or v == "" for v in padded):
            continue

        record: dict[str, Any] = {}
        unmapped: dict[str, Any] = {}

        for i, (header, value) in enumerate(zip(headers, padded)):
            if value is None or value == "":
                continue

            if column_map is None:
                record[header] = value
            else:
                col_letter = _index_to_col_letter(i)
                mapped_key = column_map.get(header) or column_map.get(col_letter)
                if mapped_key:
                    record[mapped_key] = value
                else:
                    unmapped[header] = value

        if unmapped:
            record["_unmapped"] = unmapped

        records.append(record)

    return records


def _index_to_col_letter(idx: int) -> str:
    """Convert 0-based column index back to Excel letter(s): 0→'A', 25→'Z', 26→'AA'."""
    letters = ""
    n = idx + 1
    while n:
        n, rem = divmod(n - 1, 26)
        letters = chr(ord("A") + rem) + letters
    return letters
