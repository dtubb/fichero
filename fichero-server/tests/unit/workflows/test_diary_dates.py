"""Diary dates: a page is dated by its own heading, checked, and never silently trusted (#5514).

WHY: a full review of the Marshall Diaries (a COPY; 4,292 pages) found one stored date in
ten wrong or doubtful and 211 dated entries with no date: "FEBRUARY 1918" read as 19 February,
"JANUARY 7 1918" ignored for want of a comma, "Jan." and "Decr" not read, memoranda and cash
pages dated from a money amount, every yearless page of a 1915-18 volume put in 1915, and 157
knowledge-graph claims carrying the prompt's own "YYYY-08-17" as their date. Each case below is
one row; a regression in any of them is a page that sorts in the wrong year.

The rules themselves are written once, in ``fichero_server.histdate`` (the "A page's own date"
block). Numeric dates read MONTH/DAY unless a number over 12 says otherwise (or ``day_first``).
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from fichero_server.histdate import (
    check_claim_date,
    find_page_date,
    gregorian_to_jdn,
    years_from_name,
)
from fichero_server.models import Document

V1919 = years_from_name("NCM_Diary_19190101-19191231")
V1915_18 = years_from_name("NCM_Diary_19150108-19180628")
V1943_45 = years_from_name("NCM_Diary_19431017-19450922")

# (case, page text, volume years, expected). Expected keys:
#   iso / precision / source (year_source) / flag (a date_meta key that must be set)
#   / end (iso of the range end) / invalid (substring of the reason) / none / non_entry.
CASES = [
    # --- headings the diaries actually carry
    ("full heading", "MONDAY, JANUARY 1, 1923\nWent to office", [1923],
     {"iso": "1923-01-01", "precision": "day", "source": "written"}),
    ("stray token before abbreviated weekday", "Ther FRI. JAN. 10, 1913\nWarm", [1913],
     {"iso": "1913-01-10", "source": "written"}),
    ("abbreviated heading beats a later full-name mention (sample 42)",
     "Thursday, Jan. 1, 1942\nWashington’s Birthday, Easter Monday, May 30,", [1942],
     {"iso": "1942-01-01"}),
    ("abbreviated heading beats 'October 1.' below it (sample 41)",
     "TUESDAY, SEPT. 21, 1943\nOctober 1. Mr. Ames will also record", [1943],
     {"iso": "1943-09-21"}),
    ("mention in prose below the heading (sample 43)",
     "WEDNESDAY, SEPT. 15, 1943\npills again, having stopped since July 15.", [1943],
     {"iso": "1943-09-15"}),
    ("abbreviated month 1942 (sample 44)", "WED. FEB. 11, 1942\nSnow", [1942], {"iso": "1942-02-11"}),
    ("abbreviated month 1943 (sample 45)", "THUR. FEB. 11, 1943", [1943], {"iso": "1943-02-11"}),
    ("abbreviated month Aug (sample 46)", "SUN. AUG. 16, 1942", [1942], {"iso": "1942-08-16"}),
    # --- K1: the day is never read from the year's digits
    ("month and year is a month (sample 28)", "FRIDAY, JUNE 1918\nRain", V1919,
     {"iso": "1918-06-01", "precision": "month", "flag": "volume_year_conflict"}),
    ("May 1914 is May (sample 29)", "May 1914", [1914], {"iso": "1914-05-01", "precision": "month"}),
    ("February 1913 is February (sample 30)", "February 1913", [1913],
     {"iso": "1913-02-01", "precision": "month"}),
    ("FEBRUARY 1918 is not Feb 19", "FEBRUARY 1918", [1918], {"iso": "1918-02-01", "precision": "month"}),
    # --- K2: the year with or without a comma, and the 1919 volume's "1918"
    ("no comma (sample 36)", "SUNDAY, JUNE 9 1918", V1919,
     {"iso": "1918-06-09", "source": "written", "flag": "volume_year_conflict"}),
    ("full stop before the year; weekday fits 1919 (sample 37)", "FRIDAY, JANUARY 24. 1918", V1919,
     {"iso": "1918-01-24", "flag": "weekday_conflict"}),
    ("full stop after the weekday (sample 38)", "MONDAY. OCTOBER 7 1918", V1919, {"iso": "1918-10-07"}),
    ("comma year whose weekday says 1919", "WEDNESDAY, JANUARY 15, 1918", V1919,
     {"iso": "1918-01-15", "flag": "weekday_conflict"}),
    ("no comma, volume agrees", "JANUARY 7 1918", [1918], {"iso": "1918-01-07", "source": "written"}),
    # --- K3 + K6: a yearless heading takes the volume year; the weekday picks among several
    ("weekday picks 1916 in a 1915-18 volume (sample 48)", "Friday March 17", V1915_18,
     {"iso": "1916-03-17", "source": "weekday"}),
    ("trailing weekday picks 1944 in a 1943-45 volume (sample 47)",
     "May 23 - Tuesday - left at 7 AM in car from", V1943_45, {"iso": "1944-05-23", "source": "weekday"}),
    ("no weekday in a multi-year volume is flagged ambiguous", "Novr 3", V1915_18,
     {"iso": "1915-11-03", "source": "volume", "flag": "year_ambiguous"}),
    ("one-year volume, yearless heading, inferred", "July 9", [1925],
     {"iso": "1925-07-09", "source": "volume"}),
    # 17 March 1913 was a Monday.
    ("weekday that fits no volume year is flagged", "Tuesday March 17", [1913],
     {"iso": "1913-03-17", "flag": "weekday_conflict"}),
    ("a printed year above gives its year", "1923\nMONDAY, JANUARY 1", None,
     {"iso": "1923-01-01", "source": "page"}),
    ("no year and no volume year", "Novr 3", None, {"invalid": "no year written"}),
    # --- K4: ordinals and old abbreviations
    ("ordinal + Decr", "3rd Decr 1840", None, {"iso": "1840-12-03"}),
    ("old ordinal 2d + Novr", "Novr 2d", [1913], {"iso": "1913-11-02"}),
    ("Sept. 4th", "Sept. 4th", [1913], {"iso": "1913-09-04"}),
    ("Feby", "Feby 14, 1920", None, {"iso": "1920-02-14"}),
    ("Jany", "Jany 5 1920", None, {"iso": "1920-01-05"}),
    ("Sepr", "Sepr 30, 1913", None, {"iso": "1913-09-30"}),
    # --- numeric forms: month/day by default; a number over 12 decides
    ("numeric month/day assumed", "1/3/23", [1923], {"iso": "1923-01-03", "flag": "numeric_order"}),
    ("numeric day first (>12)", "13/3/23", [1923], {"iso": "1923-03-13"}),
    ("numeric month first (>12)", "8/31/45", [1945], {"iso": "1945-08-31"}),
    ("month name with a slashed year", "Jan 3/23", [1923], {"iso": "1923-01-03"}),
    ("numeric four-digit year", "4/17/1893", None, {"iso": "1893-04-17"}),
    ("two-digit year and no volume", "1/3/23", None, {"invalid": "two-digit year"}),
    ("neither number a month", "31/13/23", [1923], {"invalid": "can be a month"}),
    # --- impossible and out-of-range dates are refused and recorded, never rolled
    ("Feb 31 is invalid, not March 3", "Feb 31, 1923", [1923], {"invalid": "no day 31"}),
    ("Feb 29 in a common year", "Feb 29", [1913], {"invalid": "no day 29"}),
    ("Feb 29 in a leap year", "Feb 29", [1912], {"iso": "1912-02-29"}),
    ("a quantity is not the year 150", "2 May 150 sacks", None, {"invalid": "year 150"}),
    ("a year after 2100", "JANUARY 7, 2150", None, {"invalid": "year 2150"}),
    # --- bare years and ranges
    ("bare year", "1913", None, {"iso": "1913-01-01", "precision": "year", "end": "1913-12-31"}),
    ("year range", "1915-18", None, {"iso": "1915-01-01", "precision": "year", "end": "1918-12-31"}),
    # --- K5: only heading-shaped lines date a page
    ("mention in prose (sample 31)", "Says he met me at Panama in July 1933,", V1943_45, {"none": True}),
    ("memoranda page (sample 32)", "MEMORANDA\nJuly 9", [1925], {"non_entry": "MEMORANDA"}),
    ("list of dates (sample 33)", "/ 26 / June 25 / July 11 / Lozano - lights Co", [1925], {"none": True}),
    ("cash page (sample 35)", "CASH ACCOUNT\n15 July 17 Dineen - also N. 210 -", [1922],
     {"non_entry": "CASH ACCOUNT"}),
    ("ledger row with no header", "15 July 17 Dineen - also N. 210 -", [1922], {"none": True}),
    ("money amount", "Telephone … October 2.00", [1930], {"none": True}),
    ("bare amount after a month", "October 2.00", [1930], {"none": True}),
    ("almanac act", "Act of August 28, 1894", [1930], {"none": True}),
    ("an entry starting 'Cash paid' is still an entry", "Cash paid to Smith\nJuly 15, 1922", [1922],
     {"iso": "1922-07-15"}),
    # --- the formats the extractor already read keep working
    ("Spanish heading after a title line", "Diario de viaje.\n17 de abril de 1893\nHoy salimos", None,
     {"iso": "1893-04-17"}),
    ("dateline after a place", "Lima, 15 de marzo de 1791", None, {"iso": "1791-03-15"}),
    ("French Republican", "12 Thermidor An II", None, {"iso": "1794-07-30"}),
    ("explicitly undated", "n.d.\n17 de abril de 1893", None, {"none": True}),
]


@pytest.mark.parametrize("case,text,volume,expected", CASES, ids=[c[0] for c in CASES])
def test_page_date_rules(case, text, volume, expected):
    finding = find_page_date(text, volume_years=volume)
    date = finding.date
    if expected.get("none"):
        assert date is None and not finding.invalid and finding.non_entry is None, case
        return
    if "non_entry" in expected:
        assert date is None and finding.non_entry == expected["non_entry"], case
        return
    if "invalid" in expected:
        assert date is None, f"{case}: an invalid heading must not date the page"
        assert finding.invalid and expected["invalid"] in finding.invalid[0]["reason"], finding.invalid
        return
    assert date is not None, f"{case}: no date ({finding})"
    meta = date.meta
    assert meta["converted_gregorian_iso"] == expected["iso"], (case, meta)
    assert meta["heading"], "the heading as written is kept"
    if "precision" in expected:
        assert meta["precision"] == expected["precision"], case
    if "source" in expected:
        assert meta.get("year_source") == expected["source"], (case, meta)
        assert meta.get("year_inferred") is (expected["source"] != "written"), case
    if "flag" in expected:
        assert meta.get(expected["flag"]), (case, meta)
    if "end" in expected:
        from fichero_server.histdate import jdn_to_gregorian_iso

        assert jdn_to_gregorian_iso(date.jdn_end) == expected["end"], case


def test_day_first_reads_an_ambiguous_numeric_date_day_month():
    """The order is a stated rule, and a corpus that writes day/month can say so."""
    date = find_page_date("1/3/23", volume_years=[1923], day_first=True).date
    assert date.meta["converted_gregorian_iso"] == "1923-03-01"
    assert date.meta["numeric_order"] == "day/month (assumed)"


def test_an_inferred_year_is_shown_as_supplied():
    """A year the page never wrote is displayed in editorial brackets, never as if written."""
    date = find_page_date("Friday March 17", volume_years=V1915_18).date
    assert date.meta["display"] == "Friday March 17 [1916]"


def test_volume_years_come_from_the_folder_name():
    assert years_from_name("NCM_Diary_19150108-19180628") == [1915, 1916, 1917, 1918]
    assert years_from_name("1923") == [1923]
    assert years_from_name("IMG_0123") == []


# --- Import: a supplied date is checked against the page's heading (#5514 K7) -----------------


def _imported(page_text: str, supplied: str) -> Document:
    from fichero_server.importers.ingest import apply_import_date

    doc = Document(id="p", name="IMG_001.jpg", page_content=page_text)
    assert apply_import_date(doc, supplied, source="manifest")
    return doc


def test_import_agreeing_with_the_heading_keeps_the_heading_beside_the_date():
    doc = _imported("MONDAY, JANUARY 1, 1923\nWent to office", "1923-01-01")
    assert doc.date_original == "1923-01-01"
    assert doc.date_meta["heading_as_written"] == "MONDAY, JANUARY 1, 1923"
    assert doc.date_meta["date_as_supplied"] == "1923-01-01"
    assert "heading_conflict" not in doc.date_meta


def test_import_disagreeing_with_the_heading_is_a_visible_conflict():
    """'JANUARY 7 1918' staged as 1919-01-07 (sample 36's shape): the supplied date is kept,
    the disagreement is recorded for the person to settle; neither is trusted silently."""
    doc = _imported("MONDAY, JANUARY 7 1918\nCold", "1919-01-07")
    assert doc.date_jdn == gregorian_to_jdn(1919, 1, 7)
    conflict = doc.date_meta["heading_conflict"]
    assert conflict["heading_date"] == "1918-01-07"
    assert conflict["supplied"] == "1919-01-07"
    assert any("heading says" in r for r in conflict["reasons"])


def test_import_day_from_the_year_digits_is_a_conflict():
    """'FEBRUARY 1918' staged as 1918-02-19 (K1): the heading gives no day."""
    doc = _imported("FEBRUARY 1918\n", "1918-02-19")
    assert "the heading gives no day" in doc.date_meta["heading_conflict"]["reasons"]


def test_import_weekday_that_does_not_fit_is_a_conflict():
    """A yearless heading is compared by month, day and weekday: 17 March 1915 was a Wednesday."""
    doc = _imported("Friday March 17\n", "1915-03-17")
    reasons = doc.date_meta["heading_conflict"]["reasons"]
    assert any("weekday (Friday)" in r for r in reasons), reasons


def test_import_onto_a_memoranda_page_is_a_conflict():
    doc = _imported("MEMORANDA\nTelephone … October 2.00", "1930-10-02")
    assert any("MEMORANDA" in r for r in doc.date_meta["heading_conflict"]["reasons"])


def test_import_with_no_page_text_is_unchanged():
    from fichero_server.importers.ingest import apply_import_date

    doc = Document(id="p", name="x.jpg")
    assert apply_import_date(doc, "1923-02-05", source="manifest")
    assert "heading_conflict" not in doc.date_meta and "heading_as_written" not in doc.date_meta


def test_an_impossible_supplied_date_is_not_applied():
    from fichero_server.importers.ingest import apply_import_date

    doc = Document(id="p", name="x.jpg")
    assert not apply_import_date(doc, "1923-02-31", source="manifest")
    assert doc.date_jdn is None


# --- Claim dates: placeholders and impossible dates are dropped, far dates flagged (K8, K9) ---


@pytest.mark.parametrize("value,ok", [
    ("1923-08-17", True), ("1923-08", True), ("1923", True), ("1923-08-17/1923-08-19", True),
    ("YYYY-08-17", False), ("YYYY-MM-25", False), ("XXXX-10-28", False), ("YYYY-11-36", False),
    ("<UNKNOWN>", False), ("1923-11-36", False), ("1923-02-29", False), ("1923-13", False),
    ("2150-01-01", False), ("1923-08-19/1923-08-17", False),
])
def test_claim_date_check(value, ok):
    checked, problem = check_claim_date(value)
    assert (checked == value) is ok and (problem is None) is ok, (value, problem)


@pytest.fixture
def svo_library(tmp_path: Path, monkeypatch):
    from tests.integration._seedlib import seed

    from fichero_server.db import db_manager
    from fichero_server.llm.language_policy import parse_policy
    from fichero_server.workflows.tools import extract_svo_only as svo

    monkeypatch.setenv("FICHERO_SKIP_DEFAULT_WORKFLOWS", "1")
    monkeypatch.setattr(svo, "configured_policy", lambda: parse_policy(None))
    library_path = tmp_path / "diary.fichero"
    seed(library_path)
    db = db_manager.get_database(library_path)
    yield library_path, db
    db_manager.close_database(library_path)


def test_claim_dates_are_validated_and_the_model_is_told_the_page_date(svo_library, monkeypatch):
    """No LLM: a stub answers as the Marshall model did. The placeholder and the impossible date
    are dropped (claims kept, dated nothing, flagged); a date years from the page is flagged; and
    the prompt names the page's date and its volume's year."""
    from fichero_server.llm import LLMConfig
    from fichero_server.models import DocType, FileType
    from fichero_server.models.knowledge import KnowledgeClaim
    from fichero_server.workflows.tools import extract_svo_only as svo

    library_path, db = svo_library
    db.save(Document(id="vol", name="NCM_Diary_19230101-19231231", doc_type=DocType.folder))
    db.save(Document(
        id="page", parent_id="vol", name="IMG_016.jpg", doc_type=DocType.file, file_type=FileType.text,
        page_content="WEDNESDAY, MARCH 14, 1923\nWrote to Dineen about the bonds due 1/1/52.",
        date_jdn=gregorian_to_jdn(1923, 3, 14), date_jdn_end=gregorian_to_jdn(1923, 3, 14),
    ))
    systems: list[str] = []

    async def fake_structured(**kwargs):
        systems.append(kwargs["system"])
        schema = kwargs["schema"]
        return schema(items=[
            {"date": "March 14", "date_normalized": "YYYY-03-14", "verb": "wrote", "object": "to Dineen"},
            {"date": "the 36th", "date_normalized": "1923-11-36", "verb": "noted", "object": "a payment"},
            {"date": "1/1/52", "date_normalized": "1952-01-01", "verb": "fall due", "object": "the bonds"},
            {"date": "March 14", "date_normalized": "1923-03-14", "verb": "records", "object": "the entry"},
        ])

    monkeypatch.setattr(svo, "chat_structured_with_fallback", fake_structured)
    asyncio.run(svo.extract_svo_only(
        {"documents": [{"id": "page"}]},
        {"library_path": str(library_path), "selected_doc_ids": ["page"], "task_id": "t"},
        LLMConfig(provider="fake", model="fake-model"),
    ))

    assert "This page is dated 1923-03-14." in systems[0]
    assert "volume covering 1923" in systems[0]
    claims = {c.metadata["date_text"] + "|" + (c.predicate_verb or ""): c
              for c in db.query(KnowledgeClaim, source_document_id="page")}
    placeholder = claims["March 14|wrote"]
    assert placeholder.time_start is None and placeholder.time_end is None
    assert placeholder.metadata["date_flags"][0]["value"] == "YYYY-03-14"
    impossible = claims["the 36th|noted"]
    assert impossible.time_start is None
    assert "no day 36" in impossible.metadata["date_flags"][0]["reason"]
    far = claims["1/1/52|fall due"]
    assert far.time_start == "1952-01-01"
    assert far.metadata["date_flags"][0]["reason"] == "more than a year from the page's own date"
    good = claims["March 14|records"]
    assert good.time_start == "1923-03-14" and "date_flags" not in good.metadata


# --- The Extract Date tool: volume year and refusals reach the page (one code path) -----------


def test_extract_date_tool_uses_the_volume_year_and_records_refusals():
    from unittest.mock import MagicMock, patch

    from fichero_server.workflows.tools.date_extract import date_extract_tool

    volume = Document(id="vol", name="NCM_Diary_19150108-19180628")
    yearless = Document(id="a", parent_id="vol", name="IMG_023", page_content="Friday March 17\nRain")
    impossible = Document(id="b", parent_id="vol", name="IMG_024", page_content="Feb 31, 1916\nx")
    memo = Document(id="c", parent_id="vol", name="IMG_099", page_content="MEMORANDA\nJuly 9")
    rows = {d.id: d for d in (volume, yearless, impossible, memo)}
    db = MagicMock()
    db.get.side_effect = lambda _model, doc_id: rows.get(doc_id)
    with patch("fichero_server.workflows.tools.date_extract.db_manager") as mgr, patch(
        "fichero_server.workflows.tools.date_extract.emit_workflow_document_changes"
    ), patch("fichero_server.workflows.tools.date_extract.emit_workflow_artifact_changes"):
        mgr.get_database.return_value = db
        asyncio.run(date_extract_tool(
            {"documents": [{"id": "a"}, {"id": "b"}, {"id": "c"}]},
            {"library_path": "/tmp/t.fichero"},
            MagicMock(),
        ))
    assert yearless.date_meta["converted_gregorian_iso"] == "1916-03-17"
    assert yearless.date_meta["year_inferred"] is True
    assert impossible.date_jdn is None
    assert "no day 31" in impossible.date_meta["invalid"][0]["reason"]
    assert memo.date_jdn is None and memo.date_meta["non_entry"] == "MEMORANDA"
