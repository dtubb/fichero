"""Merge Geometry — the reviewed text tied to the boxes we measured.

The alignment itself is tested on strings and rectangles in
tests/unit/media/test_geometry_merge.py. These pin the part that touches the
library: which artifacts get fed to it, what gets written back, and — the
thing that matters most — that a page it cannot merge is REPORTED rather than
skipped in silence, so a chain that merged four of five pages never looks
complete.
"""

from __future__ import annotations

import datetime as dt
from unittest.mock import MagicMock, patch

import pytest

from fichero_server.media.ocr_geometry import (
    OCRGeometryBox,
    OCRGeometryLevel,
    OCRGeometryResult,
)
from fichero_server.workflows.tools.merge_geometry import merge_geometry_tool

NOW = dt.datetime(2026, 8, 28, 12, 0)


def _row(**fields):
    row = MagicMock()
    row.created_at = NOW
    row.step_name = ""
    row.content = None
    row.ocr_geometry = None
    row.id = "artifact-1"
    for key, value in fields.items():
        setattr(row, key, value)
    return row


def _measured() -> OCRGeometryResult:
    def word(text, x, y):
        return OCRGeometryBox(
            text=text, bbox=[x, y, 0.08, 0.03], level=OCRGeometryLevel.WORD
        )

    return OCRGeometryResult(
        provider="apple",
        text="Don Pedro\nmstruia Popayan",
        boxes=[
            word("Don", 0.10, 0.10),
            word("Pedro", 0.20, 0.10),
            word("mstruia", 0.10, 0.20),
            word("Popayan", 0.22, 0.20),
        ],
    )


def _db(*, text_rows, geometry_rows):
    db = MagicMock()

    def query(_model, **kwargs):
        kind = kwargs.get("artifact_type")
        if kind == "transcription_review":
            return list(text_rows)
        if kind == "regions":
            return list(geometry_rows)
        return []

    db.query.side_effect = query
    return db


async def _run(db, doc_ids=("doc-1",), config=None):
    with patch("fichero_server.db.db_manager.get_database", return_value=db):
        return await merge_geometry_tool(
            {},
            {"library_path": "/tmp/lib", "selected_doc_ids": list(doc_ids),
             "task_id": "run-1"},
            None,
            config or {},
        )


class TestMergeGeometry:
    @pytest.mark.asyncio
    async def test_it_writes_one_geometry_artifact_carrying_the_reviewed_text(self):
        db = _db(
            text_rows=[_row(content="Don Pedro\ninstruía Popayán")],
            geometry_rows=[_row(ocr_geometry=_measured())],
        )
        out = await _run(db)

        assert out["count"] == 1
        saved = db.save.call_args.args[0]
        assert saved.artifact_type == "text_geometry"
        # The reviewed text, not the OCR's — otherwise the spans index a
        # string nobody is reading.
        assert saved.content == "Don Pedro\ninstruía Popayán"
        assert saved.ocr_geometry.text == "Don Pedro\ninstruía Popayán"
        assert saved.ocr_geometry.boxes
        assert out["records"][0]["measured_words"] >= 3

    @pytest.mark.asyncio
    async def test_a_document_missing_either_half_is_reported_not_skipped(self):
        db = _db(text_rows=[], geometry_rows=[_row(ocr_geometry=_measured())])
        out = await _run(db)

        assert out["count"] == 0
        db.save.assert_not_called()
        assert out["records"] == [
            {"doc_id": "doc-1", "merged": False,
             "reason": "no reviewed text artifact"}
        ]

    @pytest.mark.asyncio
    async def test_a_refused_alignment_carries_its_reason_forward(self):
        """Nothing aligns, so nothing is written — and the run says why."""
        db = _db(
            text_rows=[_row(content="zzzz\nyyyy")],
            geometry_rows=[_row(ocr_geometry=_measured())],
        )
        out = await _run(db)

        assert out["count"] == 0
        db.save.assert_not_called()
        assert out["records"][0]["merged"] is False
        assert "alignment" in out["records"][0]["reason"]

    @pytest.mark.asyncio
    async def test_an_unreadable_geometry_row_does_not_end_the_run(self):
        db = _db(
            text_rows=[_row(content="Don Pedro\ninstruía Popayán")],
            geometry_rows=[_row(ocr_geometry={"provider": None, "boxes": "nope"})],
        )
        out = await _run(db)

        assert out["count"] == 0
        assert "unreadable" in out["records"][0]["reason"]

    @pytest.mark.asyncio
    async def test_step_name_picks_which_review_pass_supplies_the_text(self):
        """Three review passes save as r1/r2/r3; the merge must be steerable."""
        db = _db(
            text_rows=[
                _row(content="wrong wrong\nwrong wrong", step_name="r1"),
                _row(content="Don Pedro\ninstruía Popayán", step_name="r3"),
            ],
            geometry_rows=[_row(ocr_geometry=_measured())],
        )
        out = await _run(db, config={"step_name": "r3"})

        assert out["count"] == 1
        assert db.save.call_args.args[0].content == "Don Pedro\ninstruía Popayán"
