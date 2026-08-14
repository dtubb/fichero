"""Diary entry splitting — REAL DuckDB, stubbed LLM.

The contract: per-day child nodes with a deterministic ISO date attribute
and the diary_entry prototype (date ROLE — the timeline/calendar feed);
per-day bbox = union of the overlapping OCR line boxes; undated entries
are recorded as undated, never guessed; re-runs replace this tool's own
children and nothing else.
"""

from unittest.mock import patch

import pytest

from fichero_server.db import Database
from fichero_server.media.ocr_geometry import OCRGeometryBox, OCRGeometryResult
from fichero_server.models import Artifact, DocType, Document
from fichero_server.models.knowledge import (
    ClassificationDimension,
    ClassificationValue,
)
from fichero_server.workflows.tools.diary_entries import (
    DiaryEntry,
    DiaryPageSplit,
    split_page_into_entries,
)

PAGE_TEXT = (
    "January 8th 1942\nCold morning. Wrote letters until noon.\n"
    "January 9th 1942\nRain all day. The convoy did not arrive."
)


@pytest.fixture
def diary_db(tmp_path):
    db = Database(path=tmp_path / "t.duckdb")
    page = Document(
        id="page-1",
        name="NCM Diary p.12",
        doc_type=DocType.file,
        page_content=PAGE_TEXT,
        metadata={"width": 1000, "height": 2000},
    )
    db.save(page)
    boxes = [
        OCRGeometryBox(text="January 8th 1942", bbox=[0.1, 0.05, 0.5, 0.04], char_start=0, char_end=16),
        OCRGeometryBox(
            text="Cold morning. Wrote letters until noon.",
            bbox=[0.1, 0.10, 0.8, 0.05], char_start=17, char_end=56,
        ),
        OCRGeometryBox(text="January 9th 1942", bbox=[0.1, 0.50, 0.5, 0.04], char_start=57, char_end=73),
        OCRGeometryBox(
            text="Rain all day. The convoy did not arrive.",
            bbox=[0.1, 0.55, 0.85, 0.05], char_start=74, char_end=114,
        ),
    ]
    db.save(
        Artifact(
            document_id="page-1",
            artifact_type="transcription",
            content=PAGE_TEXT,
            ocr_geometry=OCRGeometryResult(text=PAGE_TEXT, boxes=boxes, provider="test"),
        )
    )
    return db, page


def _split(entries):
    async def fake_chat_structured(prompt, schema, config, **kwargs):
        return DiaryPageSplit(entries=entries)

    return patch(
        "fichero_server.workflows.tools.diary_entries.chat_structured",
        side_effect=fake_chat_structured,
    )


TWO_ENTRIES = [
    DiaryEntry(
        date_text="January 8th 1942",
        date_iso="1942-01-08",
        text="January 8th 1942\nCold morning. Wrote letters until noon.",
    ),
    DiaryEntry(
        date_text="January 9th 1942",
        date_iso="1942-01-09",
        text="January 9th 1942\nRain all day. The convoy did not arrive.",
    ),
]


class TestDiaryEntries:
    @pytest.mark.asyncio
    async def test_two_dated_entries_become_child_nodes(self, diary_db):
        db, page = diary_db
        with _split(TWO_ENTRIES):
            created = await split_page_into_entries(db, page, llm_config=None)

        assert [d.name for d in created] == ["1942-01-08", "1942-01-09"]
        for node in created:
            assert node.parent_id == "page-1"
            assert node.prototype_key == "diary_entry"
            assert node.node_kind == "entry"
        assert created[0].attributes["date"] == "1942-01-08"
        assert created[1].attributes["date"] == "1942-01-09"
        assert "Cold morning" in created[0].page_content
        assert "convoy" in created[1].page_content

    @pytest.mark.asyncio
    async def test_bbox_is_union_of_the_days_line_boxes(self, diary_db):
        db, page = diary_db
        with _split(TWO_ENTRIES):
            created = await split_page_into_entries(db, page, llm_config=None)

        first, second = created[0].bbox, created[1].bbox
        assert first is not None and second is not None
        # Pixel ints against the page's 1000x2000 metadata: day one spans its
        # heading + body lines; day two starts lower; no vertical overlap.
        assert first == (100, 100, 800, 200)
        assert second == (100, 1000, 850, 200)
        assert first[1] + first[3] <= second[1]

    @pytest.mark.asyncio
    async def test_prototype_created_with_date_role(self, diary_db):
        db, page = diary_db
        with _split(TWO_ENTRIES):
            await split_page_into_entries(db, page, llm_config=None)
        rows = db.query(
            ClassificationValue,
            dimension=ClassificationDimension.document_prototype,
            key="diary_entry",
        )
        assert rows, "prototype must be created on first use"
        declaration = rows[0].attributes["date"]
        assert declaration["role"] == "date"
        assert declaration["type"] == "date"

    @pytest.mark.asyncio
    async def test_unparseable_date_stays_undated(self, diary_db):
        db, page = diary_db
        entries = [
            DiaryEntry(
                date_text="the feast of St. Unclear",
                date_iso=None,
                text="January 8th 1942\nCold morning. Wrote letters until noon.",
            )
        ]
        with _split(entries):
            created = await split_page_into_entries(db, page, llm_config=None)
        assert created[0].name == "the feast of St. Unclear"
        assert "date" not in created[0].attributes
        assert created[0].metadata["date_parsed"] is False

    @pytest.mark.asyncio
    async def test_rerun_replaces_only_this_tools_children(self, diary_db):
        db, page = diary_db
        bystander = Document(
            id="note-1", name="my note", parent_id="page-1", doc_type=DocType.file
        )
        db.save(bystander)
        with _split(TWO_ENTRIES):
            first_run = await split_page_into_entries(db, page, llm_config=None)
            second_run = await split_page_into_entries(db, page, llm_config=None)
        assert len(second_run) == 2
        live = db.query(Document, parent_id="page-1") or []
        live_ids = {d.id for d in live if d.deleted_at is None}
        assert "note-1" in live_ids, "bystander children survive re-runs"
        for stale in first_run:
            assert stale.id not in live_ids, "previous run's entries are replaced"

    @pytest.mark.asyncio
    async def test_empty_transcript_raises(self, diary_db):
        db, _ = diary_db
        blank = Document(id="page-2", name="blank", doc_type=DocType.file)
        db.save(blank)
        with _split(TWO_ENTRIES), pytest.raises(ValueError, match="no transcript"):
            await split_page_into_entries(db, blank, llm_config=None)
