"""Diary entry splitting — REAL DuckDB, stubbed LLM.

The contract: per-day child nodes with a deterministic ISO date attribute
and the diary_entry prototype (date ROLE — the timeline/calendar feed);
per-day bbox = union of the overlapping OCR line boxes; undated entries
are recorded as undated, never guessed; re-runs replace this tool's own
children and nothing else.
"""

from unittest.mock import patch

import pytest

from fichero_server.core.timeutil import utc_now
from fichero_server.db import Database
from fichero_server.media.ocr_geometry import OCRGeometryBox, OCRGeometryResult
from fichero_server.models.anchors import NodeRegion, RegionConfidence
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
            ocr_geometry=OCRGeometryResult(text=PAGE_TEXT, boxes=boxes, provider="apple"),
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

#: The same page re-extracted with the SECOND entry no longer seen — what a
#: changed transcript or a differently-behaving model produces.
ONE_ENTRY = [TWO_ENTRIES[0]]


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
    async def test_region_is_union_of_the_days_line_boxes(self, diary_db):
        db, page = diary_db
        with _split(TWO_ENTRIES):
            created = await split_page_into_entries(db, page, llm_config=None)

        first, second = created[0].region_in_parent, created[1].region_in_parent
        assert first is not None and second is not None
        # NORMALIZED fractions of the page now, not pixel ints. These are the
        # same rectangles the old assertion described — 0.1 x 1000 = 100,
        # 0.05 x 2000 = 100, and so on — with the lossy scaling step removed.
        assert first.rect == pytest.approx([0.1, 0.05, 0.8, 0.10])
        assert second.rect == pytest.approx([0.1, 0.50, 0.85, 0.10])
        # Day one ends above where day two begins: no vertical overlap.
        assert first.rect[1] + first.rect[3] <= second.rect[1]

    @pytest.mark.asyncio
    async def test_apple_boxes_are_marked_measured(self, diary_db):
        """Apple Vision DETECTS boxes from the pixels, so the union of them is
        a measurement, not a guess at where an entry might fall."""
        db, page = diary_db
        with _split(TWO_ENTRIES):
            created = await split_page_into_entries(db, page, llm_config=None)

        assert created[0].region_in_parent.confidence is RegionConfidence.measured

    @pytest.mark.asyncio
    async def test_VLM_boxes_are_marked_nominal_not_measured(self, diary_db):
        """`detect_regions` says it itself: "VLM boxes are claimed, not
        measured". A model asked for boxes and answered; nothing verified them
        against the pixels. Marking the resulting entry region `measured` would
        make a guess indistinguishable from a measurement — the exact
        distinction RegionConfidence exists to preserve."""
        db, page = diary_db
        artifact = db.query(Artifact, document_id=page.id)[0]
        artifact.provider = "openrouter"
        db.save(artifact)

        with _split(TWO_ENTRIES):
            created = await split_page_into_entries(db, page, llm_config=None)

        assert created[0].region_in_parent.confidence is RegionConfidence.nominal

    @pytest.mark.asyncio
    async def test_the_region_names_where_its_numbers_came_from(self, diary_db):
        """A region should carry WHERE its numbers came from, not merely how
        they were combined."""
        db, page = diary_db
        with _split(TWO_ENTRIES):
            created = await split_page_into_entries(db, page, llm_config=None)

        assert created[0].region_in_parent.method == "diary-entry-word-union:apple"

    @pytest.mark.asyncio
    async def test_unknown_provenance_under_claims(self, diary_db):
        """The safe default is to under-claim: a region wrongly marked
        measured tells a reader the box was verified when nobody verified
        it."""
        db, page = diary_db
        artifact = db.query(Artifact, document_id=page.id)[0]
        artifact.provider = None
        artifact.ocr_geometry.provider = "something-new"
        db.save(artifact)

        with _split(TWO_ENTRIES):
            created = await split_page_into_entries(db, page, llm_config=None)

        assert created[0].region_in_parent.confidence is RegionConfidence.nominal

    @pytest.mark.asyncio
    async def test_geometry_SURVIVES_a_page_with_no_pixel_dimensions(self, diary_db):
        """The recovered case, and the reason for the change.

        The old code scaled the normalized OCR union down into pixel ints,
        which needed the page's width/height from metadata and returned None
        without them — discarding geometry that was sitting right there. A
        normalized region never needed those dimensions.
        """
        db, page = diary_db
        page.metadata = {}
        db.save(page)

        with _split(TWO_ENTRIES):
            created = await split_page_into_entries(db, page, llm_config=None)

        assert created[0].region_in_parent is not None
        assert created[0].region_in_parent.rect == pytest.approx([0.1, 0.05, 0.8, 0.10])
        assert created[0].metadata["bbox_basis"] == "ocr_geometry"

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
    async def test_rerun_touches_only_this_tools_children(self, diary_db):
        db, page = diary_db
        bystander = Document(
            id="note-1", name="my note", parent_id="page-1", doc_type=DocType.file
        )
        db.save(bystander)
        with _split(TWO_ENTRIES):
            await split_page_into_entries(db, page, llm_config=None)
            second_run = await split_page_into_entries(db, page, llm_config=None)
        assert len(second_run) == 2
        live = db.query(Document, parent_id="page-1") or []
        live_ids = {d.id for d in live if d.deleted_at is None}
        assert "note-1" in live_ids, "bystander children survive re-runs"

    @pytest.mark.asyncio
    async def test_an_unchanged_rerun_KEEPS_the_same_nodes(self, diary_db):
        """The heart of it. This used to hard-delete every entry and recreate
        it with a new id, so a re-run that changed nothing still replaced
        everything — Daniel's "I saw no change" was true on screen while
        identity churned underneath, and anything referencing an entry was
        orphaned."""
        db, page = diary_db
        with _split(TWO_ENTRIES):
            first = await split_page_into_entries(db, page, llm_config=None)
            second = await split_page_into_entries(db, page, llm_config=None)

        assert [d.id for d in first] == [d.id for d in second]

    @pytest.mark.asyncio
    async def test_a_user_corrected_region_SURVIVES_re_extraction(self, diary_db):
        """`RegionConfidence.user` exists so a person's correction survives
        re-extraction. Delete-and-recreate defeated it every single run."""
        db, page = diary_db
        with _split(TWO_ENTRIES):
            first = await split_page_into_entries(db, page, llm_config=None)

            corrected = db.get(Document, first[0].id)
            corrected.region_in_parent = NodeRegion(
                rect=[0.05, 0.05, 0.9, 0.2],
                confidence=RegionConfidence.user,
                method="drawn-by-hand",
            )
            db.save(corrected)

            await split_page_into_entries(db, page, llm_config=None)

        after = db.get(Document, first[0].id)
        assert after.region_in_parent.confidence is RegionConfidence.user
        assert after.region_in_parent.rect == [0.05, 0.05, 0.9, 0.2]
        assert after.metadata["bbox_basis"] == "user-corrected"

    @pytest.mark.asyncio
    async def test_a_machine_region_is_still_refreshed(self, diary_db):
        """Only USER regions are protected. A nominal/measured one must keep
        improving as the geometry improves, or re-running could never fix a
        bad box."""
        db, page = diary_db
        with _split(TWO_ENTRIES):
            first = await split_page_into_entries(db, page, llm_config=None)
            machine = db.get(Document, first[0].id)
            machine.region_in_parent = NodeRegion(
                rect=[0.0, 0.0, 0.1, 0.1], confidence=RegionConfidence.nominal
            )
            db.save(machine)

            await split_page_into_entries(db, page, llm_config=None)

        after = db.get(Document, first[0].id)
        assert after.region_in_parent.rect != [0.0, 0.0, 0.1, 0.1]

    @pytest.mark.asyncio
    async def test_an_entry_that_disappears_is_SOFT_deleted(self, diary_db):
        """Daniel's ruling, after the evidence that nothing restores a hard
        delete: workflow runs write no ActionAudit and no MutationLog, and the
        "workflow snapshot" is the graph, not the data."""
        db, page = diary_db
        with _split(TWO_ENTRIES):
            first = await split_page_into_entries(db, page, llm_config=None)
        assert len(first) == 2

        with _split(ONE_ENTRY):
            await split_page_into_entries(db, page, llm_config=None)

        gone = db.get(Document, first[1].id)
        assert gone is not None, "the row must still exist to be recoverable"
        assert gone.deleted_at is not None

    @pytest.mark.asyncio
    async def test_entry_body_drops_its_date_heading(self, diary_db):
        # The heading is STRUCTURED data (node name + date_text metadata);
        # repeating it as the body's first line reads the date twice in
        # every renderer (Daniel 2026-08-15).
        from fichero_server.workflows.tools.diary_entries import (
            _body_without_date_heading,
        )

        assert _body_without_date_heading(
            "FRIDAY, JANUARY 3, 1919\nHigh river.\nSan Jose arrived.",
            "FRIDAY, JANUARY 3, 1919",
        ) == "High river.\nSan Jose arrived."
        # A body whose first line is NOT the heading is untouched.
        assert _body_without_date_heading(
            "High river.\nSan Jose arrived.", "FRIDAY, JANUARY 3, 1919"
        ) == "High river.\nSan Jose arrived."
        # Punctuation/case wobble still matches.
        assert _body_without_date_heading(
            "Friday, January 3, 1919:\nHigh river.", "FRIDAY. JANUARY 3, 1919"
        ) != ""
        # A PRINTED heading with OCR noise rarely equals date_text — the
        # structural rule catches it: caps, month, day-or-weekday
        # (2026-08-15 night: "we've got the date repeated in text").
        assert _body_without_date_heading(
            "TUESDAY, JANUARY § 7\nSan José left.", "Jan. 8"
        ) == "San José left."
        assert _body_without_date_heading(
            "MONDAY. JANUARY F. 19186 3\nWillian Hilton infured.", "Jan. 7"
        ) == "Willian Hilton infured."
        # Mixed-case prose naming the month and a day is NOT a heading.
        assert _body_without_date_heading(
            "We spent February 15 at the dredge.\nMore.", "Feb. 15"
        ) == "We spent February 15 at the dredge.\nMore."

    async def test_span_found_across_line_breaks(self, diary_db):
        # The prefix is whitespace-normalized; the geometry content has real
        # newlines. Before 2026-08-17 the raw-content search returned None
        # for any entry whose opening words cross a line break — no span, no
        # bbox ("some pages have word level bounding boxes, many don't").
        from fichero_server.workflows.tools.diary_entries import (
            DiaryEntry,
            _entry_spans,
        )

        content = "MONDAY, JANUARY 13\nSan Jose left\nPaimado today\nTUESDAY, JANUARY 14\nPay day."
        entries = [
            DiaryEntry(date_text="Jan. 13", text="San Jose left Paimado today"),
            DiaryEntry(date_text="Jan. 14", text="Pay day."),
        ]
        spans = _entry_spans(content, entries)
        assert spans[0] is not None, "line-crossing prefix must still locate"
        assert content[spans[0][0]:].startswith("San Jose left")
        assert spans[1] is not None
        # Spans are RAW offsets: entry 1 ends where entry 2 begins.
        assert spans[0][1] == spans[1][0]
        assert content[spans[1][0]:].startswith("Pay day.")

    async def test_empty_transcript_raises(self, diary_db):
        db, _ = diary_db
        blank = Document(id="page-2", name="blank", doc_type=DocType.file)
        db.save(blank)
        with _split(TWO_ENTRIES), pytest.raises(ValueError, match="no transcript"):
            await split_page_into_entries(db, blank, llm_config=None)


class TestHeadingAnchoredRegions:
    """The Marshall failure mode (2026-08-23): entries are split from the LLM
    vision transcript, but the geometry is Apple OCR — and on handwritten
    pages the OCR mangles every cursive line, so a body-prefix match found
    nothing for 128 of 201 real entries. The typeset date heading is the one
    line the OCR reads reliably, so it anchors the span; body prefixes stay
    as the fallback."""

    OCR_TEXT = (
        "SATURDAY. JANUARY 7. 1933\n"
        "dealing elenty else use t\n"        # OCR's rendering of the cursive body
        "In afternon went t Bridge\n"
        "SUNDAY. JANUARY 8. 1933\n"
        "MONDAY. JANUARY 9. 1933\n"
        "at ta yuelta ofice\n"                # more mangled cursive
    )

    def _boxes(self):
        rows = []
        cursor = 0
        y = 0.05
        for line in self.OCR_TEXT.splitlines():
            rows.append(OCRGeometryBox(
                text=line, bbox=[0.1, y, 0.7, 0.05],
                char_start=cursor, char_end=cursor + len(line),
            ))
            cursor += len(line) + 1
            y += 0.15
        return rows

    def _page_and_db(self, tmp_path):
        db = Database(path=tmp_path / "h.duckdb")
        page = Document(
            id="page-h", name="part_2", doc_type=DocType.file,
            # The LLM transcript the split runs on — CLEAN text the OCR never produced.
            page_content=(
                "SATURDAY, JANUARY 7, 1933\nWatching laboratory clean up at\n"
                "SUNDAY, JANUARY 8, 1933\n"
                "MONDAY, JANUARY 9, 1933\nAt La Vuelta office\n"
            ),
            metadata={},
        )
        db.save(page)
        db.save(Artifact(
            document_id="page-h", artifact_type="transcription", content=self.OCR_TEXT,
            ocr_geometry=OCRGeometryResult(text=self.OCR_TEXT, boxes=self._boxes(), provider="test"),
        ))
        return db, page

    ENTRIES = [
        DiaryEntry(date_text="SATURDAY, JANUARY 7, 1933", date_iso="1933-01-07",
                   text="Watching laboratory clean up at\nIn afternoon went to Bridge No.4"),
        DiaryEntry(date_text="SUNDAY, JANUARY 8, 1933", date_iso="1933-01-08",
                   text="SUNDAY, JANUARY 8, 1933"),
        DiaryEntry(date_text="MONDAY, JANUARY 9, 1933", date_iso="1933-01-09",
                   text="At La Vuelta office"),
    ]

    @pytest.mark.asyncio
    async def test_every_entry_gets_a_region_via_its_printed_heading(self, tmp_path):
        db, page = self._page_and_db(tmp_path)
        with _split(self.ENTRIES):
            created = await split_page_into_entries(db, page, llm_config=None)
        assert len(created) == 3
        for node in created:
            assert node.region_in_parent is not None, (
                f"{node.name} lost its region — the heading anchor regressed "
                "to body-prefix-only matching (mangled-OCR failure mode)"
            )
        # Bands are ordered down the page, heading to heading.
        tops = [n.region_in_parent.rect[1] for n in created]
        assert tops == sorted(tops)
        # Jan 7's band covers its heading AND its (mangled) body lines but
        # stops before Jan 8's heading.
        jan7 = created[0].region_in_parent.rect
        jan8_top = created[1].region_in_parent.rect[1]
        assert jan7[1] + jan7[3] <= jan8_top + 1e-6

    @pytest.mark.asyncio
    async def test_punctuation_difference_alone_never_loses_the_anchor(self, tmp_path):
        # Same data, but the transcript's headings use commas while the OCR
        # printed periods — the exact Marshall stationery difference.
        db, page = self._page_and_db(tmp_path)
        with _split(self.ENTRIES):
            created = await split_page_into_entries(db, page, llm_config=None)
        assert all(n.metadata.get("bbox_basis") == "ocr_geometry" for n in created)

    @pytest.mark.asyncio
    async def test_last_entry_span_reaches_the_pages_trailing_boxes(self, tmp_path):
        db, page = self._page_and_db(tmp_path)
        with _split(self.ENTRIES):
            created = await split_page_into_entries(db, page, llm_config=None)
        # Jan 9's band must include the mangled body line BELOW its heading —
        # the old span end used the NORMALIZED length as a RAW offset and cut
        # the last entry short of the page's trailing boxes.
        jan9 = created[2].region_in_parent.rect
        assert jan9[1] + jan9[3] >= 0.80, f"last entry's band stops at {jan9[1] + jan9[3]}"


class TestFlicker:
    """LLM output is not deterministic: an entry can vanish on one run and
    return on the next. Creating a fresh node on its return would lose the
    curation a second time, which defeats the point of keeping the row."""

    @pytest.mark.asyncio
    async def test_an_entry_that_returns_gets_its_OLD_node_back(self, diary_db):
        db, page = diary_db
        with _split(TWO_ENTRIES):
            first = await split_page_into_entries(db, page, llm_config=None)
        vanished_id = first[1].id

        with _split(ONE_ENTRY):
            await split_page_into_entries(db, page, llm_config=None)
        assert db.get(Document, vanished_id).deleted_at is not None

        with _split(TWO_ENTRIES):
            third = await split_page_into_entries(db, page, llm_config=None)

        assert vanished_id in {d.id for d in third}, "the id must come back"
        assert db.get(Document, vanished_id).deleted_at is None

    @pytest.mark.asyncio
    async def test_curation_survives_a_flicker(self, diary_db):
        """The reason resurrection matters at all."""
        db, page = diary_db
        with _split(TWO_ENTRIES):
            first = await split_page_into_entries(db, page, llm_config=None)
            corrected = db.get(Document, first[1].id)
            corrected.region_in_parent = NodeRegion(
                rect=[0.02, 0.5, 0.9, 0.3],
                confidence=RegionConfidence.user,
            )
            db.save(corrected)

        with _split(ONE_ENTRY):
            await split_page_into_entries(db, page, llm_config=None)
        with _split(TWO_ENTRIES):
            await split_page_into_entries(db, page, llm_config=None)

        after = db.get(Document, first[1].id)
        assert after.region_in_parent.confidence is RegionConfidence.user
        assert after.region_in_parent.rect == [0.02, 0.5, 0.9, 0.3]

    @pytest.mark.asyncio
    async def test_a_PERSON_s_deletion_is_not_undone(self, diary_db):
        """A re-run that quietly resurrected what someone deliberately deleted
        would be worse than a duplicate. Only this tool's own removals come
        back."""
        db, page = diary_db
        with _split(TWO_ENTRIES):
            first = await split_page_into_entries(db, page, llm_config=None)

        deleted_by_person = db.get(Document, first[1].id)
        deleted_by_person.deleted_at = utc_now()   # no tool-removed marker
        db.save(deleted_by_person)

        with _split(TWO_ENTRIES):
            await split_page_into_entries(db, page, llm_config=None)

        assert db.get(Document, first[1].id).deleted_at is not None
