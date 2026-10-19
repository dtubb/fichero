"""What a recipe run's review step left on its pages, for the run summary (R3, `recipes/run_view.reviewed`).

Persistence layer (#1876): the SQL lives here, behind typed functions; callers never write it. Each reads every page
in one query, however many there are (review 153).
"""

from __future__ import annotations

from typing import Any


def reviews_oldest_first(db: Any, pages: list[str]) -> list[tuple[str, str, str | None, Any]]:
    """Every transcription review of these pages: (id, page, content, data), oldest first, so the last a page sees
    is its newest; a review with no time counts as the oldest (review 156)."""
    return db.execute_fetchall(
        "SELECT id, document_id, content, data FROM artifacts WHERE artifact_type = 'transcription_review' "
        "AND document_id IN (SELECT unnest(?::VARCHAR[])) "
        "ORDER BY COALESCE(created_at, TIMESTAMP '1970-01-01'), id", [list(pages)])


def line_ids_by_page(db: Any, pages: list[str]) -> dict[str, set[str]]:
    """The line segments of these pages: page -> its line ids."""
    lines: dict[str, set[str]] = {}
    for segment_id, page in db.execute_fetchall(
            "SELECT id, document_id FROM segments WHERE kind = 'line' AND document_id IN "
            "(SELECT unnest(?::VARCHAR[]))", [list(pages)]):
        lines.setdefault(page, set()).add(segment_id)
    return lines


def lines_corrected_by(db: Any, review_ids: list[str]) -> dict[str, int]:
    """For each of these reviews, how many lines it gave a reading still standing: review id -> count."""
    return dict(db.execute_fetchall(
        "SELECT derived_from_artifact_id, count(DISTINCT segment_id) FROM contentrepresentations WHERE "
        "retracted_at IS NULL AND derived_from_artifact_id IN (SELECT unnest(?::VARCHAR[])) GROUP BY 1",
        [list(review_ids)]))
