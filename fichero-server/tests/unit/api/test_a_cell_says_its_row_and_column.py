"""A table cell's segment says its row, column and spans, in one shape (#5168).

WHY: a PAGE `TableCell`'s place was kept on import (`foreign["pagexml:row"]` and so on) because
the model has no cell fields -- which left the app reading a PAGE-specific key to show a cell's
row and column, and anything built on that would break for the next format with tables. The
read now carries `cell: {row, column, row_span, column_span}` worked out from what the file said
(storage unchanged). If this regresses, the Inspector cannot say which row and column a cell is,
or says it wrongly; the numbers are checked against the file with lxml.
"""

from __future__ import annotations

from pathlib import Path

from lxml import etree

import fichero_server.api.main  # noqa: F401  (registers every action)
from tests.unit.api.test_page_text_follows_the_file import _import

TABLE = Path(__file__).parents[1] / "formats" / "fixtures" / "transkribus_abp_table_0019.page.xml"


def _cells_by_lxml() -> list[tuple[int, int, int, int]]:
    root = etree.parse(str(TABLE)).getroot()
    return sorted(
        (int(c.get("row")), int(c.get("col")), int(c.get("rowSpan") or 1), int(c.get("colSpan") or 1))
        for c in root.iter("{*}TableCell")
    )


def test_every_cell_reads_its_place_as_the_file_states_it(db, client):
    doc_id = _import(db, TABLE)
    segments = client.get(f"/api/segments/document/{doc_id}").json()["segments"]
    cells = [s["cell"] for s in segments if s.get("cell")]
    assert len(_cells_by_lxml()) == 172
    assert sorted((c["row"], c["column"], c["row_span"], c["column_span"]) for c in cells) == _cells_by_lxml()


def test_a_segment_that_is_not_a_cell_has_none(db, client):
    doc_id = _import(db, TABLE)
    segments = client.get(f"/api/segments/document/{doc_id}").json()["segments"]
    assert all(s["cell"] is None for s in segments if s["kind"] in ("line", "word", "table"))
