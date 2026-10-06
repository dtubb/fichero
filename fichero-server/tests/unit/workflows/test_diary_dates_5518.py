"""Re-dating a whole diary project in one run (#5518).

Spec: docs/contributor_manual/specs/source/historical-text-normalization.md (histnorm.dates.*).

WHY: the fixed diary extractor (#5514) was run on a COPY of the Marshall Diaries before the
real project. One run over the whole project failed on the workflow-state cap (16.8 MB > 8 MB:
the Files source carried every page's text); folder expansion never reached 171 pages (a group,
the halves a spread was split into); English numeric dates were refused because the language an
import stated in ``metadata.language`` was never read; and seven previously correct pages got
worse (a heading after a running header, a page number after the year, a margin label beating
the full heading, a heading far down a prose page). The maintainer then ruled the 1919 volume:
when the written weekday AND the volume's year agree against a written year, they win, and the
written year is kept beside the date and flagged.

Every row uses only the heading strings from the review (no page images, no other page text):
a regression in any of them is a page that sorts on the wrong day or in the wrong year.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from fichero_server.histdate import find_page_date, years_from_name
from fichero_server.models import Document, DocType, FileType

V1919 = years_from_name("NCM_Diary_19190101-19191231")
V1915_18 = years_from_name("NCM_Diary_19150108-19180628")
V1943_45 = years_from_name("NCM_Diary_19431017-19450922")
# Running prose that leads with no date, to push a heading below the first lines.
PROSE = "\n".join(["the launch went on up the river all day"] * 24)

# (case, page text, volume years, expected): iso / source (year_source) / heading / none /
# non_entry / precision / flag (a date_meta key that must be set) / written_year.
CASES = [
    # --- the seven regressions from the copy run, each now dated as before
    ("heading after a running header (1940 IMG_023_part_2)",
     "Seattle Office. Vice-Consul. WEDNESDAY, APRIL 24, 1940\nPaid to City Treasurer\n"
     "THURSDAY, APRIL 25, 1940", [1940],
     {"iso": "1940-04-24", "source": "written", "heading": "WEDNESDAY, APRIL 24, 1940"}),
    ("a page number after the year (1919 IMG_043_part_2)",
     "SUNDAY, AUGUST 4, 1918 10\nSent the mailpack\nMONDAY, AUGUST 11", V1919,
     {"iso": "1918-08-04", "source": "written", "flag": "volume_year_conflict"}),
    ("margin label, then the full heading (1919 IMG_020_part_1)",
     "Mar. 23\nSaturday, March 23, 1918\nsick 3 days\nSunday, March 24", V1919,
     {"iso": "1918-03-23", "source": "written", "heading": "Saturday, March 23, 1918"}),
    ("margin label, heading with a slashed counter (1919 IMG_044_part_1)",
     "Aug. 14\nWEDNESDAY, AUGUST 14, 1918/3\nNo Air.", V1919, {"iso": "1918-08-14"}),
    ("margin label, heading with a slashed counter (1919 IMG_054_part_1)",
     "Oct. 13\nSUNDAY, OCTOBER 13, 1918/2\nMONDAY, OCTOBER 14, 13", V1919, {"iso": "1918-10-13"}),
    ("margin label, full heading (1919 IMG_057_part_1)",
     "Oct. 31\nTHURSDAY, OCTOBER 31, 1918\nFRIDAY, OCTOBER 31", V1919, {"iso": "1918-10-31"}),
    ("heading far down a prose page (1915-18 IMG_021)",
     PROSE + "\nSunday February 14th - Ran\naground twice", V1915_18,
     {"iso": "1915-02-14", "source": "weekday"}),
    # --- the other parser gaps
    ("trailing page number, no weekday", "MAY 13. 1918 12\nleft for the river", [1918],
     {"iso": "1918-05-13", "source": "written"}),
    ("trailing page number with weekday (1919 IMG_028_part_2)", "MONDAY, MAY 13. 1918 12", V1919,
     {"iso": "1918-05-13"}),
    ("trailing page number, no comma (1919 IMG_047_part_2)", "WEDNESDAY, SEPTEMBER 4 1918 3", V1919,
     {"iso": "1918-09-04"}),
    ("a number after a garbled heading is not a page number: the next heading dates the page",
     "THURSDAY, APRIL 5, 1918 24\nWent down to meet the launch\nFRIDAY, APRIL 25", V1919,
     {"iso": "1919-04-25", "source": "volume"}),
    ("Dec.4 with no space (1943-45 IMG_022)", "Dec.4 Saturday - returned to Bogota today.", V1943_45,
     {"iso": "1943-12-04", "source": "weekday"}),
    ("Dec.20 with no space, one-volume year", "Dec.20 Went down to the river", [1915],
     {"iso": "1915-12-20", "source": "volume"}),
    ("a written year keeps a note after it", "SUNDAY, SEPTEMBER 1, 1918 AUGUST 31", V1919,
     {"iso": "1918-09-01"}),
    # --- what must still NOT date a page
    ("a letter-register row is not a heading", "Sept.5 Sept24 June26 Newspaper clippings", [1920],
     {"none": True}),
    ("prose mentioning a full date mid-line",
     "and then we sailed for Buenaventura on Wednesday, April 24, 1940 with the cargo", [1940],
     {"none": True}),
    ("a yearless date deep in a page is a mention", PROSE + "\nJuly 9 paid the men", [1925],
     {"none": True}),
    ("an amount after a yearless date is still a ledger row", "15 July 17 Dineen - also N. 210 -", [1922],
     {"none": True}),
    # --- almanac and account pages give no diary date
    ("month-named cash page (1942 IMG_193)", "May Cash Account\nMay 1 | Div: Copper Corp | 100", [1942],
     {"non_entry": "CASH ACCOUNT"}),
    ("January cash page (1942 IMG_191)", "January Cash Account\nJan. 2 | Div: Railway | 112.50", [1942],
     {"non_entry": "CASH ACCOUNT"}),
    ("moon's phases under a month heading (1913 IMG_017)",
     "February 1913\nMOON'S PHASES.\n(In Standard Time.)", [1913], {"non_entry": "MOON'S PHASES"}),
    ("the 1894 coin table (1913 IMG_004)",
     "CALENDAR.\nVALUES OF FOREIGN COINS.\nproclaimed under the Act of August 28, 1894", [1913],
     {"non_entry": "CALENDAR"}),
    ("legal holidays (1913 IMG_011)", "MISSISSIPPI. Jan 1 Vicksburg\nLEGAL HOLIDAYS.", [1913],
     {"non_entry": "LEGAL HOLIDAYS"}),
    ("a week page with a cash column stays a month page (1914)",
     "April 1914 Cash Account Received Paid\nSun. Dinner", [1914],
     {"iso": "1914-04-01", "precision": "month"}),
    # --- the 1919 rule: weekday AND volume year agree against the written year
    ("weekday + volume beat the written year (sample 37)", "FRIDAY, JANUARY 24. 1918", V1919,
     {"iso": "1919-01-24", "source": "weekday_and_volume", "written_year": 1918}),
    ("same, comma form", "WEDNESDAY, JANUARY 15, 1918", V1919,
     {"iso": "1919-01-15", "source": "weekday_and_volume", "written_year": 1918}),
    ("same, no comma", "MONDAY, JANUARY 27 1918", V1919,
     {"iso": "1919-01-27", "source": "weekday_and_volume", "written_year": 1918}),
    ("the weekday agrees with the written year: it stays, flagged against the volume",
     "SUNDAY, JUNE 9 1918", V1919, {"iso": "1918-06-09", "source": "written",
                                    "flag": "volume_year_conflict"}),
    # 2 January 1923 was a Tuesday: the volume does not disagree, so the written year stays.
    ("a written year inside the volume is never overruled", "MONDAY, JANUARY 2, 1923", [1923],
     {"iso": "1923-01-02", "source": "written", "flag": "weekday_conflict"}),
    ("with no volume year the weekday alone does not overrule", "FRIDAY, JANUARY 24. 1918", None,
     {"iso": "1918-01-24", "source": "written", "flag": "weekday_conflict"}),
]


@pytest.mark.parametrize("case,text,volume,expected", CASES, ids=[c[0] for c in CASES])
def test_marshall_redating_rules(case, text, volume, expected):
    finding = find_page_date(text, volume_years=volume)
    date = finding.date
    if expected.get("none"):
        assert date is None and finding.non_entry is None, (case, date and date.meta)
        return
    if "non_entry" in expected:
        assert date is None and finding.non_entry == expected["non_entry"], (case, finding)
        return
    assert date is not None, f"{case}: no date ({finding})"
    meta = date.meta
    assert meta["converted_gregorian_iso"] == expected["iso"], (case, meta)
    if "source" in expected:
        assert meta.get("year_source") == expected["source"], (case, meta)
    if "heading" in expected:
        assert date.original == expected["heading"], (case, date.original)
    if "precision" in expected:
        assert meta["precision"] == expected["precision"], (case, meta)
    if "flag" in expected:
        assert meta.get(expected["flag"]), (case, meta)
    if "written_year" in expected:
        assert meta["written_year"] == expected["written_year"], (case, meta)


def test_an_overruled_year_is_kept_and_shown_as_supplied():
    """The heading as written survives; the year the date took is in brackets, and why is
    recorded: a person can see the diarist wrote 1918 and why the page sorts in 1919."""
    date = find_page_date("FRIDAY, JANUARY 24. 1918\nExpress Box went down.", volume_years=V1919).date
    assert date.original == "FRIDAY, JANUARY 24. 1918"
    assert date.meta["display"] == "FRIDAY, JANUARY 24. 1918 [1919]"
    assert date.meta["year_inferred"] is True
    assert date.meta["year_overruled"] == {"written": 1918, "weekday": "Friday",
                                           "volume_years": [1919, 1919], "chosen": 1919}
    assert "weekday_conflict" not in date.meta


# --- G3: the language an import stated is read -------------------------------------------------


def test_the_language_in_imported_metadata_is_the_documents_own():
    from fichero_server.llm.language_policy import SOURCE_METADATA, read_document_language

    stated = read_document_language(Document(id="p", name="x", metadata={"language": "en-US"}))
    assert stated.language == "en-US" and stated.source == SOURCE_METADATA and stated.is_known
    recorded = read_document_language(
        Document(id="p", name="x", language="es", metadata={"language": "en-US"}))
    assert recorded.language == "es", "a language recorded on the document outranks its metadata"
    placeholder = read_document_language(Document(id="p", name="x", metadata={"language": "und"}))
    assert placeholder.language is None


def _run_date_extract(library_path: str, docs: list[Document]) -> dict:
    from unittest.mock import MagicMock, patch

    from fichero_server.workflows.tools.date_extract import date_extract_tool

    rows = {d.id: d for d in docs}
    db = MagicMock()
    db.get.side_effect = lambda _model, doc_id: rows.get(doc_id)
    with patch("fichero_server.workflows.tools.date_extract.db_manager") as mgr, patch(
        "fichero_server.workflows.tools.date_extract.emit_workflow_document_changes"
    ), patch("fichero_server.workflows.tools.date_extract.emit_workflow_artifact_changes"):
        mgr.get_database.return_value = db
        return asyncio.run(date_extract_tool(
            {"documents": [{"id": d.id} for d in docs]}, {"library_path": library_path}, MagicMock(),
        ))


def test_extract_date_reads_the_numeric_order_from_metadata_language(tmp_path: Path):
    """en-US in the page's metadata reads 11/5/43 month/day. The Marshall pages carry bare
    "en" (the staging script writes "language": "en"), which by the rule settles nothing:
    those pages keep both readings and stay undated until a person or the project setup says
    en-US or en-GB."""
    american = Document(id="us", name="a", page_content="11/5/43\nLeft by plane",
                        metadata={"language": "en-US"})
    marshall = Document(id="en", name="b", page_content="11/5/43\nLeft by plane",
                        metadata={"language": "en"})
    volume = Document(id="vol", name="NCM_Diary_19430101-19431231", doc_type=DocType.folder)
    american.parent_id = marshall.parent_id = "vol"
    _run_date_extract(str(tmp_path / "p.fichero"), [volume, american, marshall])
    assert american.date_meta["converted_gregorian_iso"] == "1943-11-05"
    assert marshall.date_jdn is None
    assert [r["date"] for r in marshall.date_meta["ambiguous"][0]["readings"]] == [
        "1943-05-11", "1943-11-05"]


# --- G2 + G1: one run over the whole project ---------------------------------------------------


@pytest.fixture
def diary_library(tmp_path: Path, monkeypatch):
    from tests.integration._seedlib import seed

    from fichero_server.db import db_manager

    monkeypatch.setenv("FICHERO_SKIP_DEFAULT_WORKFLOWS", "1")
    library_path = tmp_path / "diary.fichero"
    seed(library_path)
    db = db_manager.get_database(library_path)
    yield library_path, db
    db_manager.close_database(library_path)


def _page(db, doc_id: str, parent: str, text: str = "", doc_type: DocType = DocType.page,
          path: str | None = None, seq: int = 1) -> Document:
    doc = Document(id=doc_id, parent_id=parent, name=doc_id, doc_type=doc_type,
                   file_type=FileType.image if path else None,
                   path=path if path is not None else f"files/{doc_id}.jpg",
                   page_content=text, sequence=seq)
    db.save(doc)
    return doc


def test_folder_expansion_reaches_every_page_under_the_scope(diary_library):
    """G2: a group's pages ("Stack of 10"), the halves under a split spread (the 1932 volume's
    148), and a page with no file of its own are all reached; a diary entry under a page and a
    region are not pages and are not work units."""
    from fichero_server.workflows.tools.sources import _resolve_selection_pairs

    library_path, db = diary_library
    db.save(Document(id="root", name="Marshall Diaries", doc_type=DocType.folder))
    db.save(Document(id="v1932", parent_id="root", name="NCM_Diary_19320101-19321231",
                     doc_type=DocType.folder))
    _page(db, "plain", "v1932")
    _page(db, "spread", "v1932")
    _page(db, "half1", "spread", seq=1)
    _page(db, "half2", "spread", seq=2)
    db.save(Document(id="entry", parent_id="half1", name="1932-02-06", doc_type=DocType.file,
                     page_content="SAT. FEB. 6"))
    db.save(Document(id="region", parent_id="half1", name="r", doc_type=DocType.chunk))
    db.save(Document(id="stack", parent_id="root", name="Stack of 10", doc_type=DocType.group))
    _page(db, "s1", "stack")
    _page(db, "s2", "stack")
    db.save(Document(id="textonly", parent_id="spread", name="t", doc_type=DocType.page,
                     page_content="SAT. FEB. 6, 1932"))

    pairs = _resolve_selection_pairs(db, ["root"], str(library_path))
    reached = sorted(d.id for _, d in pairs)
    assert reached == sorted(["plain", "spread", "half1", "half2", "textonly", "s1", "s2"]), reached
    paths = {d.id: path for path, d in pairs}
    assert paths["textonly"] == paths["spread"], "a page with no file borrows its spread's path"

    group_alone = _resolve_selection_pairs(db, ["stack"], str(library_path))
    assert sorted(d.id for _, d in group_alone) == ["s1", "s2"], "a selected group is expanded"


def test_one_run_over_a_whole_project_stays_under_the_state_cap(diary_library, monkeypatch):
    """G1: the Files source as Work Out Dates configures it passes references, not every
    page's text, so a project whose pages total more than the 8 MB cap runs as ONE run, and
    the date tool's own output stays small. The cap itself is unchanged, and the full dump
    still trips it, which is what made the whole-project run fail."""
    from fichero_server.workflows.tools.date_extract import date_extract_tool
    from fichero_server.workflows.tools.sources import files_tool
    from fichero_server.workflows.types import _STATE_OUTPUT_MAX_BYTES, compact_output_for_state

    library_path, db = diary_library
    monkeypatch.setattr(
        "fichero_server.workflows.tools.date_extract.emit_workflow_document_changes",
        lambda *a, **k: None)
    monkeypatch.setattr(
        "fichero_server.workflows.tools.date_extract.emit_workflow_artifact_changes",
        lambda *a, **k: None)
    assert _STATE_OUTPUT_MAX_BYTES == 8 * 1024 * 1024
    db.save(Document(id="vol", name="NCM_Diary_19400101-19401231", doc_type=DocType.folder))
    body = "\n" + ("Paid to City Treasurer for pavement in front of my lot. " * 700)
    pages = 260  # about 40 KB of text each: over 10 MB of page text in all
    for i in range(pages):
        _page(db, f"p{i:03d}", "vol", text="WEDNESDAY, APRIL 24, 1940" + body, seq=i)
    state = {"library_path": str(library_path), "selected_doc_ids": ["vol"]}

    full = asyncio.run(files_tool({}, state, None))
    with pytest.raises(ValueError, match="capped serialized size"):
        compact_output_for_state(full)

    preset = json.loads((Path(__file__).resolve().parents[3] / "src/fichero_server/resources/"
                         "default_workflows/work_out_dates.json").read_text())
    files_config = next(n["config"] for n in preset["nodes"] if n["tool"] == "files")
    assert files_config == {"documents_as": "refs"}, "the preset passes references"

    refs = asyncio.run(files_tool(dict(files_config), state, None))
    compact_output_for_state(refs)
    assert refs["count"] == pages and "page_content" not in refs["documents"][0]

    dates = asyncio.run(date_extract_tool({"documents": refs["documents"]}, state, None))
    compact_output_for_state(dates)
    assert dates["dates"][0]["date"] == "1940-04-24"
    assert "meta" not in dates["dates"][0], "the full record lives on the page and its artifact"
    dated = db.get(Document, "p000")
    assert dated.date_meta["converted_gregorian_iso"] == "1940-04-24"
    assert dated.date_meta["heading"] == "WEDNESDAY, APRIL 24, 1940"
