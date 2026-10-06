"""A multi-year volume's year follows page order; the last heading shapes; covers (#5557).

Spec: docs/contributor_manual/specs/source/historical-text-normalization.md (histnorm.dates.*).

WHY: the #5518 rerun on a fresh clone of the Marshall Diaries left about 50 wrong years, all
in the two volumes that span several years. A yearless heading took the volume's FIRST year:
48 of the 1915-18 volume's 50 dated pages were 1915 though its months wrap December to
January three times, and the 1943-45 volume had 16 pages in Feb-Sep 1943, before the volume
begins on 17 October 1943. The tool dated each page alone; it now takes each volume's pages
in reading order and passes the previous dated page's date on. Beside that: the 1919 volume's
margin labels a day off its full heading, the "MONDAY. 1918 MARCH 31" form, OCR damage read
only when the weekday confirms; account, memoranda and memo pages still dated; and covers
("Jan 1, 1932 - Dec 31, 1932") dated 1 January.

Every heading string is the real one from the review dump (first lines of the page).
"""

from __future__ import annotations

import asyncio
import random

import pytest

from fichero_server.histdate import (
    find_page_date,
    gregorian_to_jdn,
    range_from_name,
    years_from_name,
)
from fichero_server.models import DocType, Document

V1915_18 = "NCM_Diary_19150108-19180628"
V1919 = "NCM_Diary_19190101-19191231"
V1943_45 = "NCM_Diary_19431017-19450922"


def _years(name: str) -> list[int]:
    return years_from_name(name)


def _date(text: str, volume: str, previous: str | None = None):
    """The page's date with its volume's years and range, and the previous page's date."""
    prev = None
    if previous:
        y, m, d = (int(p) for p in previous.split("-"))
        prev = gregorian_to_jdn(y, m, d)
    return find_page_date(text, volume_years=_years(volume), volume_range=range_from_name(volume),
                          previous=prev)


# --- the volume's full date range --------------------------------------------------------------


def test_a_volume_name_gives_its_first_and_last_day():
    start, end = range_from_name(V1943_45)
    assert (start, end) == (gregorian_to_jdn(1943, 10, 17), gregorian_to_jdn(1945, 9, 22))
    assert range_from_name("NCM_Diary_1923") is None, "a year alone is not a range of days"
    assert range_from_name("NCM_Diary_19431317-19450922") is None, "month 13 is no date"
    assert range_from_name("NCM_Diary_19450922-19431017") is None, "a range ends after it starts"


def test_a_yearless_heading_never_falls_before_its_volume_begins():
    """With no page before it (a page dated alone), "Feb 27" in the volume that begins 17 Oct
    1943 is 1944, the first year that keeps it inside the volume, not 1943."""
    date = _date("Feb 27 Met Dallaway here at the hotel.\nI have not yet gotten my plane", V1943_45).date
    assert date.meta["converted_gregorian_iso"] == "1944-02-27"
    assert date.meta["year_inferred"] is True


def test_a_weekday_still_decides_with_no_page_before():
    date = _date("Feb 13 Tuesday. Called at Avianca office to see about", V1943_45).date
    assert date.meta["converted_gregorian_iso"] == "1945-02-13"
    assert date.meta["year_source"] == "weekday"


# --- page order --------------------------------------------------------------------------------

# (case, page text, volume, previous page's date, expected iso, expected year_source)
PAGE_ORDER = [
    ("the month goes back, December to February: a new year (1915-18 IMG_034)",
     "Feb. 15 Back to Battle Creek\nthis morning.", V1915_18, "1915-12-31", "1916-02-15", "page_order"),
    ("Thanksgiving was the day before: 30 Nov 1916, so Dec. 1 is 1916 (IMG_045)",
     "Dec. 1 Yesterday was Thanks.\ngiving Day. I went", V1915_18, "1916-07-19", "1916-12-01",
     "page_order"),
    ("Dec. to Jan. again (IMG_047)", "Jan 23 Worked all day on the engine but could not get it to run.",
     V1915_18, "1916-12-23", "1917-01-23", "page_order"),
    ("a few months back is a page out of place, not a new year (IMG_043 'July 19th' after Sept. 10)",
     "Mosquito net on my cot.\nFelucca moved up on the\n15th but Sims & Quirk have\n"
     "been sleeping here since\nJuly 19th", V1915_18, "1916-09-10", "1916-07-19", "page_order"),
    ("forward in the same year (1943-45 IMG_024)",
     "Apr 10 AR Paterson came in the afternoon. He", V1943_45, "1944-04-07", "1944-04-10",
     "page_order"),
    ("Dec. to Apr.: the next year, 1944, not 1943 (1943-45 IMG_023)",
     "At Morgan.\n- Annual meeting. Nicholas & Co auditors.\nApr 7 Left Glen Ridge on DeKamp bus at 6",
     V1943_45, "1943-12-04", "1944-04-07", "page_order"),
    ("a weekday that fits the page-order year confirms it (1943-45 IMG_025)",
     "Apr. 15 Saturday. Announcement in evening", V1943_45, "1944-04-10", "1944-04-15", "page_order"),
    ("a weekday chooses the next year, a year the diarist skipped (1943-45 IMG_090)",
     "Oct. 10 Wed. Brought aily home with me for\ndinner this evening.", V1943_45, "1944-09-06",
     "1945-10-10", "weekday"),
    ("the last year of a volume never runs past its end: the year that keeps it inside",
     "Oct. 22 Taxi and porter to Hotel Prado $2.00", V1943_45, "1945-02-28", "1944-10-22",
     "page_order"),
]


@pytest.mark.parametrize("case,text,volume,previous,iso,source", PAGE_ORDER,
                         ids=[c[0] for c in PAGE_ORDER])
def test_a_yearless_heading_takes_its_year_from_page_order(case, text, volume, previous, iso, source):
    date = _date(text, volume, previous).date
    assert date is not None, case
    assert date.meta["converted_gregorian_iso"] == iso, (case, date.meta)
    assert date.meta["year_source"] == source, (case, date.meta)
    assert date.meta["year_inferred"] is True
    assert date.meta["display"].endswith(f"[{iso[:4]}]"), "the supplied year is shown as supplied"


def test_a_weekday_its_own_page_contradicts_does_not_move_the_year():
    """1915-18 IMG_023 sits between 17 Feb and 17 Apr 1915. "Friday March 17" fits only 1916,
    but the page's next heading, "Tuesday March 23rd", fits only 1915: the weekdays disagree,
    so page order holds, and the conflict is recorded for the historian."""
    date = _date("Friday March 17\nTuesday March 23rd\nWent to work today for the", V1915_18,
                 "1915-02-17").date
    assert date.meta["converted_gregorian_iso"] == "1915-03-17"
    assert date.meta["weekday_conflict"] == {"written": "Friday", "years_that_fit": [1916],
                                             "page_order_year": 1915}


def test_a_weekday_that_fits_no_year_is_flagged_and_page_order_holds():
    """1943-45 IMG_053: "Oct. 24 Friday" between 23 and 25 Oct 1944; 24 Oct was a Friday in
    none of the volume's years."""
    text = ("to collect 86,000 pesos which the suit to\ndefend their mines had cost them.\n"
            "Oct. 24 Friday. Went to the American Consulate to have")
    date = _date(text, V1943_45, "1944-10-23").date
    assert date.meta["converted_gregorian_iso"] == "1944-10-24"
    assert date.meta["weekday_conflict"]["years_that_fit"] == []


def test_a_written_year_is_never_moved_by_page_order():
    date = _date("January 8, 1915.\nLeft Noughton Hall at 9:30", V1915_18, "1918-06-28").date
    assert date.meta["converted_gregorian_iso"] == "1915-01-08"
    assert date.meta["year_source"] == "written"


def test_a_single_year_volume_is_unchanged_by_page_order():
    """Page order only chooses among a volume's years; one year leaves nothing to choose."""
    date = _date("Dec 31 Arrived at Kansas City", "NCM_Diary_1923", "1923-12-31").date
    assert date.meta["converted_gregorian_iso"] == "1923-12-31"
    assert _date("Jan 2 Went down", "NCM_Diary_1923", "1923-12-31").date.meta[
        "converted_gregorian_iso"] == "1923-01-02"


# --- the tool takes each volume's pages in reading order ---------------------------------------


def _run(docs: list[Document], order: list[str]) -> dict:
    from unittest.mock import MagicMock, patch

    from fichero_server.workflows.tools.date_extract import date_extract_tool

    rows = {d.id: d for d in docs}
    db = MagicMock()
    db.get.side_effect = lambda _model, doc_id: rows.get(doc_id)
    with patch("fichero_server.workflows.tools.date_extract.db_manager") as mgr, patch(
        "fichero_server.workflows.tools.date_extract.emit_workflow_document_changes"
    ), patch("fichero_server.workflows.tools.date_extract.emit_workflow_artifact_changes"), patch(
        "fichero_server.workflows.tools.date_extract._project_languages", lambda _p: []
    ):
        mgr.get_database.return_value = db
        return asyncio.run(date_extract_tool(
            {"documents": [{"id": i} for i in order]}, {"library_path": "/p.fichero"}, MagicMock()))


# (page name, heading text, expected iso or None): the 1915-18 volume, in its own order.
VOLUME_1915_18 = [
    ("IMG_016", "ARSHALL\nJANUARY- 1915.\nto\nJune 28, 1918.", "1918-06-28"),
    ("IMG_017", "January 8, 1915.\nLeft Noughton Hall at 9:30", "1915-01-08"),
    ("IMG_022", "Wednesday Feb. 17th\nLeft Nepue at 12:30 n small", "1915-02-17"),
    ("IMG_023", "Friday March 17\nTuesday March 23rd\nWent to work today for the", "1915-03-17"),
    ("IMG_033", "Dec 31 Arrived at Kansas City at 8:30 this morning, father,", "1915-12-31"),
    ("IMG_034", "Feb. 15 Back to Battle Creek\nthis morning.", "1916-02-15"),
    ("IMG_041", "for some lunch and left at\nran out of gasoline just\n12:00 midnight. Passed Noanemah\n"
                "above Munguido. Left launch\nSept. 10 at 4:50. Farwado morning we", "1916-09-10"),
    ("IMG_043", "Mosquito net on my cot.\nFelucca moved up on the\n15th but Sims & Quirk have\n"
                "been sleeping here since\nJuly 19th", "1916-07-19"),
    ("IMG_045", "Dec. 1 Yesterday was Thanks.\ngiving Day. I went", "1916-12-01"),
    ("IMG_047", "Jan 23 Worked all day on the engine but could not get it to run.", "1917-01-23"),
    ("IMG_066", "Dec.20 Went down to Duraco\ntoday with Radigan.", "1917-12-20"),
    ("IMG_067", "Jan. 26 Unloading and erecting derrick\nFinished erecting the derrick.", "1918-01-26"),
    ("IMG_072", "June 11 Arrived at Balboa at 10:30\nAM. went to Hotel Tivoli.", "1918-06-11"),
]


def _volume(name: str, pages: list[tuple[str, str, str | None]]) -> list[Document]:
    volume = Document(id=name, name=name, doc_type=DocType.folder)
    docs = [volume]
    for page, text, _iso in pages:
        docs.append(Document(id=f"{name}_{page}", parent_id=name, name=f"{name}_{page}",
                             doc_type=DocType.page, page_content=text))
    return docs


@pytest.mark.parametrize("shuffle", [False, True], ids=["in order", "shuffled"])
def test_the_tool_dates_a_multi_year_volume_in_page_order(shuffle):
    """However the source hands the pages over, the tool takes them in the volume's reading
    order (natural name order: IMG_9 before IMG_10), so 1915-18 rolls into 1916, 1917 and 1918
    at each December-to-January wrap, as the acceptance on #5557 lists."""
    docs = _volume(V1915_18, VOLUME_1915_18)
    order = [d.id for d in docs[1:]]
    if shuffle:
        random.Random(5557).shuffle(order)
    out = _run(docs, order)
    got = {d.id: d.date_meta.get("converted_gregorian_iso") for d in docs[1:]}
    assert got == {f"{V1915_18}_{p}": iso for p, _t, iso in VOLUME_1915_18}
    assert all("page_content" not in row and "meta" not in row for row in out["dates"]), \
        "the output stays references and dates, never text (G1)"


def test_the_tool_keeps_a_volume_inside_its_range():
    """1943-45: none of the volume's pages before 17 Oct 1943 (the 16 Feb-Sep 1943 pages)."""
    pages = [
        ("IMG_001", "Diary of arshall\nOct 17, 1943 - Sep 22, 1945\nNCM_Diary_19430922", "1943-10-17"),
        ("IMG_022", "Dec.4 Saturday - Sampar returned to Bogota today.", "1943-12-04"),
        ("IMG_023", "At Morgan.\n- Annual meeting.\nApr 7 Left Glen Ridge on DeKamp bus at 6", "1944-04-07"),
        ("IMG_042", "Sept 22 With Dr. Mendoza Amaro, called on Dr. Humberto Homey Barayo at",
         "1944-09-22"),
        ("IMG_056", "Feb 13 Tuesday. Called at Avianca office to see about", "1945-02-13"),
        ("IMG_057", "Feb 27 Met Dallaway here at the hotel.", "1945-02-27"),
        ("IMG_060", "Mar 12 Arrived at Buenaventura at 2:15", "1945-03-12"),
    ]
    docs = _volume(V1943_45, pages)
    _run(docs, [d.id for d in reversed(docs[1:])])
    got = {d.id: d.date_meta.get("converted_gregorian_iso") for d in docs[1:]}
    assert got == {f"{V1943_45}_{p}": iso for p, _t, iso in pages}
    cover = docs[1]
    assert cover.date_meta["precision"] == "range", "the cover is the volume's span, not a day"


def test_a_split_spread_s_halves_follow_their_spread():
    """The 1932 volume's halves sit under their spread's page: the place in reading order is
    the spread's, then the half's own sequence (before its name)."""
    volume = Document(id="v", name="NCM_Diary_19310101-19321231", doc_type=DocType.folder)
    spread_a = Document(id="a", parent_id="v", name="IMG_009", doc_type=DocType.page, page_content="")
    spread_b = Document(id="b", parent_id="v", name="IMG_010", doc_type=DocType.page, page_content="")
    halves = [
        Document(id="a2", parent_id="a", name="IMG_009_a", doc_type=DocType.page, sequence=2,
                 page_content="Dec. 30 Went to the office"),
        Document(id="a1", parent_id="a", name="IMG_009_b", doc_type=DocType.page, sequence=1,
                 page_content="Dec. 2 FRIDAY Back at the office"),  # 2 Dec 1932 was a Friday
        Document(id="b1", parent_id="b", name="IMG_010_l", doc_type=DocType.page, sequence=1,
                 page_content="Jan. 4 Went to the office"),
    ]
    docs = [volume, spread_a, spread_b, *halves]
    _run(docs, ["b1", "a2", "a1", "a", "b"])
    rows = {d.id: d for d in docs}
    assert rows["a1"].date_meta["converted_gregorian_iso"] == "1932-12-02"
    assert rows["a2"].date_meta["converted_gregorian_iso"] == "1932-12-30"
    assert rows["b1"].date_meta["converted_gregorian_iso"] == "1932-01-04", \
        "a year past the volume's end is never given: the year that keeps it inside"


def test_a_user_pinned_date_carries_into_the_next_page():
    docs = _volume(V1915_18, [("IMG_033", "a page the user dated", None),
                              ("IMG_034", "Feb. 15 Back to Battle Creek", "1917-02-15")])
    pinned = docs[1]
    pinned.date_jdn = pinned.date_jdn_end = gregorian_to_jdn(1916, 12, 31)
    pinned.date_meta = {"status": "dated", "source": "user", "precision": "day"}
    _run(docs, [d.id for d in docs[1:]])
    assert docs[2].date_meta["converted_gregorian_iso"] == "1917-02-15"


# --- the 1919 volume: the heading's day, the last shapes ---------------------------------------

DAY_1919 = [
    ("a margin label a day off the full heading below it (IMG_013_part_1)",
     "Feb. 9\nSATURDAY, FEBRUARY 8 1918\nLow river again\nSUNDAY, FEBRUARY 9", "1919-02-08"),
    ("same, August (IMG_045_part_1)",
     "Aug. 20\nTUESDAY, AUGUST 19 1918\nSent Mercenario to Buenaventura to bring back\n"
     "WEDNESDAY, AUGUST 20", "1919-08-19"),
    ("the year before the month (IMG_021_part_2)",
     "MONDAY. 1918 MARCH 31\nMills left Pasadena.\nSan Jose arrived Carmelo\nTUESDAY, APRIL 1",
     "1919-03-31"),
    ("same, with a comma (IMG_026_part_2)",
     "WEDNESDAY, 1918 APRIL 30\nHayes ditto\nTHURSDAY, MAY 1", "1919-04-30"),
    ("a month the OCR cut short, the weekday confirming (IMG_052_part_2)",
     "FRIDAY, OCTOBE 3\nSan Pablo arrived in Panama under tow.\nSATURDAY, OCTOBER 4", "1919-10-03"),
    ("a day run into its year, the weekday confirming 21 Feb 1918 (IMG_015_part_1)",
     "THURSDAY, FEBRUARY 21918\nSent three extra West India Co. up to dredge No. 1.\n"
     "FRIDAY, FEBRUARY 22 21", "1918-02-21"),
]


@pytest.mark.parametrize("case,text,iso", DAY_1919, ids=[c[0] for c in DAY_1919])
def test_1919_headings(case, text, iso):
    date = _date(text, V1919).date
    assert date is not None, case
    assert date.meta["converted_gregorian_iso"] == iso, (case, date.meta)


def test_ocr_damage_is_read_only_when_the_weekday_confirms():
    # 3 Oct 1919 was a Friday, not a Monday: the cut month is not read, the next heading dates.
    date = _date("MONDAY, OCTOBE 3\nSan Pablo arrived\nSATURDAY, OCTOBER 4", V1919).date
    assert date.meta["converted_gregorian_iso"] == "1919-10-04"
    # Neither 2 Feb 1918 nor 21 Feb 1918 was a Monday: the run of digits is not a date.
    assert _date("MONDAY, FEBRUARY 21918", V1919).date is None
    # A cut month with no weekday is not a heading at all.
    assert _date("OCTOBE 3\nSan Pablo arrived", V1919).date is None


def test_a_margin_label_beside_its_own_full_heading_keeps_its_day():
    """1941 IMG_035_part_1: the full heading of the day is on the label's own line; the next
    full heading, a day later, is the page's second entry and must not win."""
    text = ("July 9 Bill's birthday -15 WEDNESDAY, JULY 9, 1941\n"
            "Saul called 4PM. Help should arrive at Panama today.\nTHURSDAY, JULY 10, 1941")
    date = find_page_date(text, volume_years=[1941]).date
    assert date.meta["converted_gregorian_iso"] == "1941-07-09"


# --- pages that are not entries ----------------------------------------------------------------

NON_ENTRY = [
    ("a cut month over the cash columns (1914 IMG_050)",
     "Novembe\nCash Account Received Paid\nSun. 29\nMon. 30\nTues. December 1", [1914], "CASH ACCOUNT"),
    ("the printed MEMORANDA head in OCR debris (1929 IMG_075_part_2)",
     "Act with MEMORANDA very\nDATE 1924 RECEIVED PAID\nApr. 30 Rec check from very, on Cali 175.00",
     [1929], "MEMORANDA"),
    ("the year's recapitulation (1942 IMG_197)",
     "Recapitulation\nReceipts Payments\nJanuary 1586.10 16472.45", [1942], "RECAPITULATION"),
]


@pytest.mark.parametrize("case,text,years,marker", NON_ENTRY, ids=[c[0] for c in NON_ENTRY])
def test_non_entry_pages_stay_undated(case, text, years, marker):
    finding = find_page_date(text, volume_years=years)
    assert finding.date is None and finding.non_entry == marker, (case, finding)


def test_a_week_page_under_its_month_and_year_keeps_its_month():
    """1914 IMG_022: "May 1914" above the cash columns is a week of entries, dated May 1914."""
    date = find_page_date("May 1914\nCash Account Received Paid\nSun. 17\nMon. 18", volume_years=[1914]).date
    assert date.meta["precision"] == "month" and date.meta["converted_gregorian_iso"] == "1914-05-01"


MENTIONS = [
    ("a passport memo of 1926 in the 1929 diary (IMG_065_part_2)",
     "assport #274620 dated at Washington\nAugust 5, 1926. - NCM - Pauline Williams. Cancelled.\n"
     "Ley sobre Opciones. Oct. 23/24. Ley 51 de 1918. $10.00", [1929]),
    ("a year line of 1924 in the 1927 diary (IMG_004_part_1)",
     "Concrete Mixer\nArrived here March 10,\n1924.\nChanged out April 3 - .", [1927]),
    ("a mention of 1937 in the 1939 diary (IMG_071_part_1)",
     "Seabra sent. - Medical exam.\nMade at Andagoya Nov. 12, 1937 by Dr. Rodriguez & Dr. Perez\n"
     "Third perito - Dr. Uribe since made his examination\nin April - 1938\n"
     "Dr. Uribe since first arrived at Andagoya May - 1937.\n"
     "NCM had not been Gerente Chief - since Feb. - 1938, but\nreappointed Gerente Dec. 1937.", [1939]),
]


@pytest.mark.parametrize("case,text,years", MENTIONS, ids=[c[0] for c in MENTIONS])
def test_a_date_of_another_year_does_not_date_the_page(case, text, years):
    assert find_page_date(text, volume_years=years).date is None, case


def test_a_two_digit_year_outside_the_volume_is_refused():
    """1943-45 IMG_015: "11/16/23" is not 1923; refused and recorded, the page undated."""
    finding = _date("11/16/23\nHis way to Bogota. Met one of the Germania\nNov.17 Wednesday.", V1943_45)
    assert finding.date is None
    assert "none of the volume's years" in finding.invalid[0]["reason"]


def test_the_year_before_the_volume_is_not_a_mention():
    """The 1919 volume's printed "STANDARD DIARY 1918" and its "1918" headings are the 1919
    rule's business, not mentions of another year."""
    assert find_page_date("STANDARD\nDIARY\n1918", volume_years=[1919]).date.meta[
        "converted_gregorian_iso"] == "1918-01-01"
    assert find_page_date("SUNDAY, JUNE 9 1918", volume_years=[1919]).date is not None


# --- covers ------------------------------------------------------------------------------------

COVERS = [
    ("Diary of arshall\nJan 1, 1932 - Dec 31, 1932\nNCM_Diary_19321231", "NCM_Diary_19320101-19321231",
     ("1932-01-01", "1932-12-31")),
    ("DIARY OF NC MARSHALL\nJANUARY 1, 1920 TO DECEMBER 31, 1920\nNCM_DIARY_19201231",
     "NCM_Diary_19200101-19201231", ("1920-01-01", "1920-12-31")),
    ("Diary of arshall\nOct 17, 1943 - Sep 22, 1945\nNCM_Diary_19430922", V1943_45,
     ("1943-10-17", "1945-09-22")),
]


@pytest.mark.parametrize("text,volume,span", COVERS, ids=[c[1] for c in COVERS])
def test_a_cover_range_is_the_volume_span_not_its_first_day(text, volume, span):
    from fichero_server.histdate import jdn_to_gregorian_iso

    date = _date(text, volume).date
    assert date.meta["precision"] == "range"
    assert (jdn_to_gregorian_iso(date.jdn), jdn_to_gregorian_iso(date.jdn_end)) == span
    assert date.meta["display"] == date.original, "shown as written"


def test_a_cover_range_is_the_volume_span_when_the_name_gives_none():
    """A volume named by its year alone ("NCM_Diary_1932") learns its span from its cover, and a
    later page's yearless heading is kept inside it."""
    volume = Document(id="v", name="NCM_Diary_1931-1932", doc_type=DocType.folder)
    cover = Document(id="c", parent_id="v", name="IMG_001", doc_type=DocType.page,
                     page_content="Diary of arshall\nJun 1, 1931 - May 31, 1932")
    page = Document(id="p", parent_id="v", name="IMG_002", doc_type=DocType.page,
                    page_content="Feb. 3 Went to the office")
    _run([volume, cover, page], ["p", "c"])
    assert cover.date_meta["precision"] == "range"
    assert page.date_meta["converted_gregorian_iso"] == "1932-02-03"


def test_an_imported_date_is_still_checked_against_a_heading_of_another_year():
    """At import the supplied date stands in for the volume, and a heading years away from it
    is the conflict to report, not a mention to skip (the import check opts out of the rule)."""
    from fichero_server.importers.ingest import apply_import_date

    doc = Document(id="p", name="IMG_065_part_2.jpg",
                   page_content="August 5, 1926. - NCM - Pauline Williams. Cancelled.")
    assert apply_import_date(doc, "1929-08-05", source="manifest")
    conflict = doc.date_meta["heading_conflict"]
    assert conflict["heading_date"] == "1926-08-05"
    assert any("heading says" in r for r in conflict["reasons"])
