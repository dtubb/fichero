"""#3322 histdate core: golden conversions, range semantics, honest absence.

A document written in 1893 sorts by 1893, not by scan date. The sort key is
a Julian Day Number — an int; the tests assert no datetime enters the path.
The three kinds of "no date" stay distinct: extracted, explicitly undated
(n.d./s.f. — a fact about the manuscript), and none found.
"""

from __future__ import annotations

import pytest

from fichero_server.histdate import (
    STATUS_NONE_FOUND,
    STATUS_UNDATED_EXPLICIT,
    extract_date_from_text,
    french_republican_to_jdn,
    gregorian_to_jdn,
    hebrew_to_jdn,
    is_explicitly_undated,
    islamic_to_jdn,
    jdn_to_gregorian,
    julian_to_jdn,
    parse_historical_date,
)
from fichero_server.models import Document
from fichero_server.workflows.tools.date_extract import resolve_document_date


class TestGoldenConversions:
    def test_thermidor_an_ii_is_30_july_1794(self):
        d = parse_historical_date("12 Thermidor An II")
        assert d is not None
        assert d.meta["converted_gregorian_iso"] == "1794-07-30"
        assert d.meta["calendar_system"] == "french_republican"
        assert d.jdn == d.jdn_end  # day precision

    def test_1752_cutover_11_day_skip(self):
        """2 Sep 1752 (Julian) and 14 Sep 1752 (Gregorian) were ADJACENT."""
        before = parse_historical_date("2 September 1752", assume_julian=True)
        after = parse_historical_date("14 September 1752")
        assert after.jdn - before.jdn == 1

    def test_old_style_double_year(self):
        """'10 Feb 1723/4' = Julian 1724-02-10 (historical year), +11 days
        to Gregorian."""
        d = parse_historical_date("10 Feb 1723/4", year_start_march=True)
        assert d is not None
        assert d.jdn == julian_to_jdn(1724, 2, 10)
        assert d.meta["converted_gregorian_iso"] == "1724-02-21"

    def test_hebrew_and_islamic_converters(self):
        # 1 Tishri 5554 AM falls in Gregorian autumn 1793.
        assert jdn_to_gregorian(hebrew_to_jdn(5554, 7, 1))[0] == 1793
        # 1 Muharram 1211 AH falls in Gregorian 1796.
        assert jdn_to_gregorian(islamic_to_jdn(1211, 1, 1))[0] == 1796

    def test_regnal_year(self):
        d = parse_historical_date("3 Geo. II")
        assert d is not None
        assert d.meta["precision"] == "year"
        assert jdn_to_gregorian(d.jdn)[0] in (1728, 1729)  # Julian year start

    def test_era_name(self):
        d = parse_historical_date("康熙三年")
        assert d is not None
        assert d.meta["precision"] == "year"
        assert jdn_to_gregorian(d.jdn)[0] == 1664

    def test_spanish_diary_date(self):
        d = parse_historical_date("17 de abril de 1893")
        assert d.meta["converted_gregorian_iso"] == "1893-04-17"

    def test_roundtrip_identity(self):
        for ymd in [(1893, 4, 17), (1752, 9, 14), (1, 1, 1), (2026, 8, 2)]:
            assert jdn_to_gregorian(gregorian_to_jdn(*ymd)) == ymd

    def test_jdn_is_an_int_never_a_datetime(self):
        """Timezone immunity by construction: the sort key is an int."""
        d = parse_historical_date("12 Thermidor An II")
        assert isinstance(d.jdn, int) and isinstance(d.jdn_end, int)
        assert french_republican_to_jdn(2, 11, 12) == d.jdn


class TestRangeSemantics:
    def test_imprecise_dates_are_ranges(self):
        month = parse_historical_date("March 1791")
        day = parse_historical_date("15 March 1791")
        year = parse_historical_date("1791")
        assert month.jdn < month.jdn_end
        assert year.jdn < year.jdn_end
        assert day.jdn == day.jdn_end
        # Containment: the day falls inside both ranges.
        assert month.jdn <= day.jdn <= month.jdn_end
        assert year.jdn <= month.jdn <= year.jdn_end

    def test_month_sorts_before_its_days_by_start_jdn(self):
        """'March 1791' (range start = 1 Mar) precedes '15 March 1791'."""
        month = parse_historical_date("March 1791")
        day = parse_historical_date("15 March 1791")
        assert month.jdn < day.jdn

    def test_circa_flags_precision(self):
        d = parse_historical_date("circa 1791")
        assert d.meta["precision"] == "circa"
        assert d.meta["confidence"] < 0.8


class TestHonestAbsence:
    """'no date found' and 'explicitly undated' are different facts."""

    @pytest.mark.parametrize("marker", ["n.d.", "N.D.", "s.f.", "s. f.", "sine data", "sin fecha", "undated"])
    def test_archival_undated_markers(self, marker):
        assert is_explicitly_undated(marker)

    def test_a_date_is_not_undated(self):
        assert not is_explicitly_undated("17 de abril de 1893")

    def test_resolve_distinguishes_the_three_states(self):
        dated = Document(name="d", page_content="Diario. 17 de abril de 1893.")
        undated = Document(name="u", page_content="n.d.\nSome manuscript text")
        nothing = Document(name="n", page_content="Text with no date anywhere at all")

        parsed, status = resolve_document_date(dated)
        assert status == "dated" and parsed is not None

        parsed, status = resolve_document_date(undated)
        assert status == STATUS_UNDATED_EXPLICIT and parsed is None

        parsed, status = resolve_document_date(nothing)
        assert status == STATUS_NONE_FOUND and parsed is None

    def test_created_at_is_never_substituted(self):
        """The import timestamp must not leak into the historical date."""
        doc = Document(name="n", page_content="no date here")
        parsed, status = resolve_document_date(doc)
        assert parsed is None
        # And metadata fallback only fires on date-ish keys, never created_at.
        doc2 = Document(name="n2", page_content="", source_metadata={"created_at": "2026-08-02"})
        parsed2, status2 = resolve_document_date(doc2)
        assert parsed2 is None and status2 == STATUS_NONE_FOUND

    def test_metadata_date_is_used_and_labelled(self):
        doc = Document(name="m", page_content="", source_metadata={"date": "1791"})
        parsed, status = resolve_document_date(doc)
        assert status == "dated"
        assert parsed.meta["source"] == "metadata"


class TestExtractionFromRunningText:
    def test_finds_the_header_date(self):
        d = extract_date_from_text("Diario de viaje.\n17 de abril de 1893\nHoy salimos...")
        assert d is not None and d.meta["converted_gregorian_iso"] == "1893-04-17"

    def test_undated_first_line_yields_none(self):
        assert extract_date_from_text("n.d.\n17 de abril de 1893") is None

    def test_gibberish_yields_none(self):
        assert extract_date_from_text("wholly dateless prose") is None


class TestToolFailsLoudOnNothing:
    """#4467 discipline: the tool must never complete green over nothing."""

    @pytest.mark.asyncio
    async def test_no_documents_raises(self):
        from unittest.mock import MagicMock

        from fichero_server.workflows.tools.date_extract import date_extract_tool

        with pytest.raises(ValueError, match="no documents resolved"):
            await date_extract_tool({}, {"library_path": "/tmp/x.fichero"}, MagicMock())

    @pytest.mark.asyncio
    async def test_no_library_raises(self):
        from unittest.mock import MagicMock

        from fichero_server.workflows.tools.date_extract import date_extract_tool

        with pytest.raises(ValueError, match="no library_path"):
            await date_extract_tool({"documents": [{"id": "d"}]}, {}, MagicMock())

    def test_tool_is_registered_and_executable(self):
        """Registered-but-never-loadable is the use_fuzzy_match shape."""
        from fichero_server.workflows.registry import (
            _ensure_tools_loaded,
            get_tool_def,
        )

        _ensure_tools_loaded()
        tool = get_tool_def("date_extract")
        assert tool is not None and tool.uses_llm is False


class TestColumnsPersist:
    """Declared model fields — the extra='allow' silent-drop trap (#4426)."""

    def test_date_fields_round_trip_through_model_dump(self):
        doc = Document(
            name="d",
            date_original="17 de abril de 1893",
            date_jdn=2412570,
            date_jdn_end=2412570,
            date_meta={"status": "dated", "precision": "day"},
        )
        dumped = doc.model_dump()
        assert dumped["date_jdn"] == 2412570
        assert dumped["date_meta"]["status"] == "dated"
        restored = Document.model_validate(dumped)
        assert restored.date_original == "17 de abril de 1893"


class TestUserDatesSurviveReExtraction:
    """Step 5b: a user assertion is a persistent rule the extractor consults.

    Today's data-loss shape, closed: a historian corrects a date, someone
    re-runs extraction across the library, and without this the correction
    is silently gone — worse than the original bug, because the user
    believes they fixed it. The extractor still runs; disagreement is
    RECORDED (candidate preserved), never silently resolved either way.
    """

    @staticmethod
    def _run_tool(doc):
        import asyncio
        from unittest.mock import MagicMock, patch

        from fichero_server.workflows.tools.date_extract import date_extract_tool

        db = MagicMock()
        db.get.return_value = doc
        saved = []
        db.save.side_effect = saved.append
        with patch(
            "fichero_server.workflows.tools.date_extract.db_manager"
        ) as mgr, patch(
            "fichero_server.workflows.tools.date_extract.emit_workflow_document_changes"
        ):
            mgr.get_database.return_value = db
            result = asyncio.run(
                date_extract_tool(
                    {"documents": [{"id": doc.id}]},
                    {"library_path": "/tmp/t.fichero"},
                    MagicMock(),
                )
            )
        return result, saved

    def _pinned_doc(self, **meta_extra):
        return Document(
            id="doc-pinned",
            name="d",
            page_content="Diario. 17 de abril de 1893. Hoy...",  # extractor sees THIS
            date_original="3 de mayo de 1892",  # the user's correction
            date_jdn=gregorian_to_jdn(1892, 5, 3),
            date_jdn_end=gregorian_to_jdn(1892, 5, 3),
            date_meta={"status": "dated", "source": "user", "precision": "day", **meta_extra},
        )

    def test_reextraction_does_not_overwrite_a_user_date(self):
        doc = self._pinned_doc()
        result, _saved = self._run_tool(doc)
        assert doc.date_original == "3 de mayo de 1892", (
            "the user's correction was stomped by re-extraction — the "
            "data-loss shape this rule exists to prevent"
        )
        assert doc.date_jdn == gregorian_to_jdn(1892, 5, 3)
        record = result["dates"][0]
        assert record["status"] == "user_pinned"

    def test_disagreement_is_recorded_not_discarded(self):
        doc = self._pinned_doc()
        result, _ = self._run_tool(doc)
        conflict = doc.date_meta.get("extraction_conflict")
        assert conflict is not None, "a disagreement the user cannot see is a fact destroyed"
        assert conflict["candidate"]["meta"]["converted_gregorian_iso"] == "1893-04-17"
        assert result["dates"][0]["conflict"] is True
        assert "1 with a conflicting" in result["text"]

    def test_agreement_clears_a_stale_conflict(self):
        doc = self._pinned_doc(extraction_conflict={"candidate": None, "found_at": "x"})
        # Make the manuscript agree with the user's assertion.
        doc.page_content = "3 de mayo de 1892"
        self._run_tool(doc)
        assert "extraction_conflict" not in doc.date_meta

    def test_user_asserted_undated_is_pinned_too(self):
        doc = Document(
            id="doc-und",
            name="d",
            page_content="17 de abril de 1893",  # extractor WOULD find this
            date_meta={"status": STATUS_UNDATED_EXPLICIT, "source": "user"},
        )
        result, _ = self._run_tool(doc)
        assert doc.date_jdn is None, "user said undated; extraction must not date it"
        assert doc.date_meta["status"] == STATUS_UNDATED_EXPLICIT
        assert doc.date_meta["extraction_conflict"]["candidate"] is not None
        assert result["dates"][0]["status"] == "user_pinned"

    def test_user_undated_and_manuscript_undated_are_different_claims(self):
        """source distinguishes 'the manuscript says n.d.' (extracted) from
        'a user asserts this is undated' (user)."""
        manuscript = Document(id="m", name="m", page_content="n.d.\ntext")
        _result, _ = self._run_tool(manuscript)
        assert manuscript.date_meta["status"] == STATUS_UNDATED_EXPLICIT
        assert manuscript.date_meta["source"] == "extracted"
        # The user-asserted form (written by document.set_date) carries user.
        asserted = {"status": STATUS_UNDATED_EXPLICIT, "source": "user"}
        assert asserted["source"] != manuscript.date_meta["source"]


class TestOneOrderingEverywhere:
    """#3322: the library asks the SERVER for document_date order — one key,
    histdate.document_date_sort_key, shared by Database.search and the
    listing routes. A client comparator on dateJdn would compile, look
    right, and carry different tie-breaking; this pins the single source."""

    def _docs(self):
        from datetime import datetime, timezone

        day = Document(
            id="day", name="day", date_jdn=2375283, date_jdn_end=2375283,
            date_meta={"status": "dated", "precision": "day"},
        )
        month = Document(
            id="month", name="month", date_jdn=2375283, date_jdn_end=2375299,
            date_meta={"status": "dated", "precision": "month"},
        )
        earlier = Document(
            id="earlier", name="earlier", date_jdn=2375269, date_jdn_end=2375269,
            date_meta={"status": "dated", "precision": "day"},
        )
        undated = Document(
            id="undated", name="undated",
            created_at=datetime(1998, 1, 1, tzinfo=timezone.utc),
        )
        return day, month, earlier, undated

    def test_key_orders_jdn_then_precision_then_fallback(self):
        from fichero_server.histdate import document_date_sort_key, gregorian_to_jdn

        day, month, earlier, undated = self._docs()
        ordered = sorted([month, undated, day, earlier], key=document_date_sort_key)
        assert [d.id for d in ordered] == ["earlier", "day", "month", "undated"], (
            "equal start-JDNs put the precise date first; undated docs fall "
            "back to created_at converted to a JDN"
        )
        assert document_date_sort_key(undated)[0] == gregorian_to_jdn(1998, 1, 1)

    def test_listing_sort_uses_the_shared_key(self):
        from fichero_server.api.routes.document.documents import _apply_listing_sort

        day, month, earlier, undated = self._docs()
        out = _apply_listing_sort([month, undated, day, earlier], "document_date", "asc")
        assert [d.id for d in out] == ["earlier", "day", "month", "undated"]
        out_desc = _apply_listing_sort([month, day], "document_date", "desc")
        assert [d.id for d in out_desc] == ["month", "day"]

    def test_absent_sort_by_is_exactly_todays_behaviour(self):
        from fichero_server.api.routes.document.documents import _apply_listing_sort

        items = list(self._docs())
        assert _apply_listing_sort(items, None, "asc") is items, (
            "the hot path must not pay for an ordering nobody asked for"
        )

    def test_wrong_values_are_loud_400s(self):
        from fastapi import HTTPException

        from fichero_server.api.routes.document.documents import _apply_listing_sort

        with pytest.raises(HTTPException) as caught:
            _apply_listing_sort([], "name", "asc")
        assert caught.value.status_code == 400
        assert "client-side" in caught.value.detail
        with pytest.raises(HTTPException):
            _apply_listing_sort([], "document_date", "sideways")
