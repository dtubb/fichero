"""The whole-page segment list issues a bounded number of SQL queries, not one per segment (perf-optimize, 2026-11-27).

Measured on a 3,000-shape generated page at origin/integration: 1,056 queries for one `GET /api/segments/document/{id}`,
one `db.get(Segment, ...)` per segment with a reading (`retired_readings_of` looked each row up again although
`counting_answers` held every row), and the page read took 1.4 s. The query-count ratchet keeps the FEWEST count an endpoint
showed in a session, so it cannot see a count that grows with the page; this case holds one real page to a flat bound.
"""
from __future__ import annotations

import perf_ratchet

from fichero_server.models import Segment
from tests.unit.api.test_page_text_follows_the_file import CLM, _import

ROUTE_KEY = "queries.GET./api/segments/document/{doc_id}"
BOUND = 40  # measured after the fix: 20 on this 121-line page (862 before); one query a line is a regression


def _count_queries(client, test_package, monkeypatch, url: str) -> int:
    from fichero_server.db.manager import db_manager

    monkeypatch.setenv("FICHERO_PERF_RATCHET", "1")
    db_manager.close_database(test_package)  # the counter wraps a connection when it OPENS
    db_manager.get_database(test_package)
    perf_ratchet._query_session.pop(ROUTE_KEY, None)
    r = client.get(url)
    assert r.status_code == 200, r.text
    count = perf_ratchet._query_session.pop(ROUTE_KEY, None)
    assert count is not None, "the request was not counted"
    return count


def test_the_whole_page_read_issues_a_flat_number_of_queries(db, client, test_package, monkeypatch):
    doc_id = _import(db, CLM)
    lines = sum(1 for s in db.all(Segment) if s.kind == "line")
    assert lines > BOUND, "the page must have more lines than the bound, or a query a line would pass"
    count = _count_queries(client, test_package, monkeypatch, f"/api/segments/document/{doc_id}")
    assert count <= BOUND, f"{count} queries for a {lines}-line page: the read grows with the page"
