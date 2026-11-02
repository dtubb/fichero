"""The run summary's "What to check" block (`designer.how.what-to-check`, #6052): the pages a reading step is least sure of, at most five.

Certainty only, for a reader whose lines carry `machine_confidence` (a CTC reader such as Kraken). A vision-language reader's pages (the
highest insertion rate against Kraken's reading, or the lines the order check re-asked) and a deterministic step's proposals are not
listed here yet: such a page has no certainty, so it is never named by a figure it does not have."""
from __future__ import annotations

from typing import Any

MOST_PAGES = 5
#: A line under this certainty counts as one the reader was unsure of.
UNSURE_BELOW = 0.5


def least_sure(db: Any, pages: list[str], limit: int = MOST_PAGES) -> list[dict[str, Any]]:
    """The pages with the lowest mean certainty over their read lines, lowest first: `{page_id, certainty, lines_unsure, lines}`."""
    from fichero_server.models import ContentRepresentation

    by_page: dict[str, list[float]] = {}
    for row in db.query_in(ContentRepresentation, "document_id", pages) if pages else []:
        if row.kind != "transcription" or not row.segment_id or row.retracted_at or row.machine_confidence is None:
            continue
        by_page.setdefault(row.document_id, []).append(float(row.machine_confidence))
    scored = [{"page_id": page, "certainty": round(sum(c) / len(c), 3), "lines_unsure": sum(1 for x in c if x < UNSURE_BELOW), "lines": len(c)}
              for page, c in by_page.items()]
    return sorted(scored, key=lambda s: (s["certainty"], s["page_id"]))[:limit]
