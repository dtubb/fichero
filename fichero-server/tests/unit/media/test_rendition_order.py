"""Rendition display order — decided once, engine-side.

Every surface that flips between renditions must agree what "next" means. If
the preview and a canvas card each sort locally, they will eventually
disagree, and the user is the one who reconciles it. These prove the single
definition.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fichero_server.media.rendition_order import (
    displayable,
    order_renditions,
    primary_rendition,
)
from fichero_server.models import Rendition


def _rendition(role: str, **kwargs) -> Rendition:
    kwargs.setdefault("document_id", "doc-1")
    kwargs.setdefault("path", f"/{role}.jpg")
    return Rendition(role=role, **kwargs)


class TestOrdering:
    def test_role_preference_decides_when_nothing_is_primary(self):
        """The staging pipeline often labels nothing; preference order is the
        fallback, not an arbitrary insertion order."""
        rows = [_rendition("original"), _rendition("enhanced"), _rendition("rotated")]
        assert [r.role for r in order_renditions(rows)] == [
            "enhanced",
            "rotated",
            "original",
        ]

    def test_primary_wins_over_role_preference(self):
        rows = [_rendition("enhanced"), _rendition("original", is_primary=True)]
        assert order_renditions(rows)[0].role == "original"

    def test_unknown_role_sorts_last_but_is_never_dropped(self):
        """Roles are free-form so staging can invent them. A rendition nobody
        ranked is still one the user can look at — hiding it would be the
        absence-read-as-answer mistake."""
        rows = [_rendition("hocr_overlay"), _rendition("enhanced")]
        ordered = order_renditions(rows)
        assert [r.role for r in ordered] == ["enhanced", "hocr_overlay"]
        assert len(ordered) == 2

    def test_same_role_ties_break_deterministically(self):
        """Two enhanced passes must not swap places between calls, or
        'press down twice' stops being a stable gesture."""
        older = _rendition(
            "enhanced", id="b", created_at=datetime(2026, 1, 1, tzinfo=timezone.utc)
        )
        newer = _rendition(
            "enhanced", id="a", created_at=datetime(2026, 6, 1, tzinfo=timezone.utc)
        )
        assert [r.id for r in order_renditions([newer, older])] == ["b", "a"]
        assert [r.id for r in order_renditions([older, newer])] == ["b", "a"]

    def test_empty_list_is_empty_not_an_error(self):
        assert order_renditions([]) == []


class TestPrimary:
    def test_returns_the_marked_primary(self):
        marked = _rendition("original", is_primary=True)
        assert primary_rendition([_rendition("enhanced"), marked]).id == marked.id

    def test_falls_back_to_preference_when_none_marked(self):
        rows = [_rendition("original"), _rendition("enhanced")]
        assert primary_rendition(rows).role == "enhanced"

    def test_none_for_a_node_with_no_renditions(self):
        """Ordinary, not an error — folders have none. The CALLER decides
        whether that is a problem, because only it knows if it was about to
        render something."""
        assert primary_rendition([]) is None


class TestDisplayable:
    def test_unmaterialized_rows_are_skipped(self):
        """Kept in the model as a knowable state, but a flip sequence should
        not show a placeholder every second press."""
        rows = [
            _rendition("enhanced"),
            _rendition("original", materialized=False),
        ]
        assert [r.role for r in displayable(rows)] == ["enhanced"]

    def test_displayable_preserves_order(self):
        rows = [_rendition("original"), _rendition("enhanced"), _rendition("crop")]
        assert [r.role for r in displayable(rows)] == ["enhanced", "crop", "original"]

    def test_all_unmaterialized_is_empty(self):
        rows = [_rendition("enhanced", materialized=False)]
        assert displayable(rows) == []
