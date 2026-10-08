"""`source.extract.entries-are-units` (#5601): a diary entry is the set of lines it covers; its text is read
from them, not copied.

Through the real paths: a page's lines imported from PAGE XML (`format.import`), its page reading tied to
those lines by the tie job (`POST /api/check/runs`, Kraken faked at its seam as in
`tests/unit/check/test_tie_text_to_lines.py`), then the Diary Entries split (`diary_entries`, the one
splitter `split_pages_into_entries`) with its model stubbed at `chat_structured`; everything read back
through `GET /api/documents/{id}/children` and `GET /api/documents/{id}`, a line corrected through
`POST /api/content-representations`.

What breaks without these: an entry that keeps a copy of the page text and a rectangle, so a line a
historian corrects reads one way on the page and the old way in the day's entry, and nothing says which
lines the day is written on.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from PIL import Image

from fichero_server.actions.registry import ActionContext, registry
from fichero_server.llm import LLMConfig
from fichero_server.models import Artifact, DocType, Document, FileType, Status
from fichero_server.models.segments import SegmentPass
from fichero_server.workflows.tools.diary_entries import (
    NOT_TIED,
    TEXT_FROM_LINES,
    DiaryEntry,
    DiaryPageSplit,
    diary_entries,
)
from tests.unit.check.test_tie_text_to_lines import _lines, _run, reader  # noqa: F401  (fixture)
from tests.unit.training.test_kraken_training_set import TEACHER

BOOT = ActionContext(actor="historian", library_path=None, is_bootstrap=True)
LINES = (
    "January 8th 1942",
    "Cold morning. Wrote letters",
    "until noon.",
    "January 9th 1942",
    "Rain all day. The convoy did not arrive.",
)
ENTRIES = [
    DiaryEntry(date_text="January 8th 1942", date_iso="1942-01-08",
               text="January 8th 1942\nCold morning. Wrote letters\nuntil noon."),
    DiaryEntry(date_text="January 9th 1942", date_iso="1942-01-09",
               text="January 9th 1942\nRain all day. The convoy did not arrive."),
]


def _page_xml(width: int, height: int) -> str:
    lines = []
    for i, text in enumerate(LINES):
        top = 20 + i * 60
        lines.append(
            f'<TextLine id="l{i}" custom="readingOrder {{index:{i};}}">'
            f'<Coords points="20,{top} 580,{top} 580,{top + 40} 20,{top + 40}"/>'
            f'<Baseline points="20,{top + 32} 580,{top + 32}"/>'
            f"<TextEquiv><Unicode>{text}</Unicode></TextEquiv></TextLine>"
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<PcGts xmlns="http://schema.primaresearch.org/PAGE/gts/pagecontent/2013-07-15">'
        "<Metadata><Creator>test</Creator><Created>2026-10-08T00:00:00</Created>"
        "<LastChange>2026-10-08T00:00:00</LastChange></Metadata>"
        f'<Page imageFilename="diary.jpg" imageWidth="{width}" imageHeight="{height}">'
        '<TextRegion id="r0" custom="readingOrder {index:0;}">'
        f'<Coords points="10,10 590,10 590,{height - 10} 10,{height - 10}"/>'
        + "".join(lines)
        + "</TextRegion></Page></PcGts>"
    )


@pytest.fixture
def page(db, tmp_path, jobs_run_by_the_test):
    """A diary page whose lines Kraken found, read whole by a model (the page's only text)."""
    folder = Document(name="Diary 1942", doc_type=DocType.folder)
    db.save(folder)
    size = (600, 340)
    photo = tmp_path / "diary.jpg"
    Image.new("RGB", size, (220, 220, 210)).save(photo)
    doc = Document(name="diary.jpg", doc_type=DocType.file, file_type=FileType.image, path=str(photo),
                   parent_id=folder.id, status=Status.completed)
    db.save(doc)
    xml = tmp_path / "diary.xml"
    xml.write_text(_page_xml(*size), encoding="utf-8")
    registry.invoke(db, "format.import", {"document_id": doc.id, "path": str(xml)}, BOOT)
    (kraken,) = db.query(SegmentPass, document_id=doc.id)
    kraken.model = "kraken-blla"
    db.save(kraken)
    text = "\n".join(LINES)
    doc = db.get(Document, doc.id)
    doc.page_content = text  # what the splitter reads, the same words the reading holds
    db.save(doc)
    reading = Artifact(document_id=doc.id, artifact_type="transcription", content=text, model=TEACHER,
                       provider="openrouter")
    db.save(reading)
    return {"folder": folder, "doc": doc, "kraken": kraken, "text": text, "reading": reading}


def _ok(response):
    assert response.status_code == 200, response.text
    return response.json()


async def _split(test_package, page):
    async def answer(prompt, schema, config, **kwargs):
        return DiaryPageSplit(entries=ENTRIES)

    with patch("fichero_server.workflows.tools.diary_entries.chat_structured", side_effect=answer):
        return await diary_entries(
            {"documents": [{"id": page["doc"].id}]},
            {"library_path": str(test_package)},
            LLMConfig(provider="openai", model="gpt-4o-mini"),
        )


def _entries(client, page):
    items = _ok(client.get(f"/api/documents/{page['doc'].id}/children"))["items"]
    return sorted((i for i in items if i.get("node_kind") == "entry"), key=lambda i: i["sequence"])


@pytest.mark.asyncio
async def test_an_entry_names_the_lines_it_covers_and_reads_its_text_from_them(
        client, db, test_package, page, reader):
    """source.extract.entries-are-units: "an entry is a logical unit over the lines it covers; its text is
    read from those lines". WHY: from a day, the reader goes to the lines it is written on; a correction
    made on a line is the day's text at once, with no second copy to fall behind."""
    _job, status = _run(client, db, page)
    assert status["counts"]["tied"] == len(LINES)
    line = [row.id for row in _lines(db, page["kraken"].id)]

    result = await _split(test_package, page)
    assert result["created_count"] == 2
    assert "on 3 lines" in result["text"] and "on 2 lines" in result["text"]

    first, second = _entries(client, page)
    assert first["metadata"]["lines"] == line[:3] and second["metadata"]["lines"] == line[3:]
    assert first["metadata"]["text_from"] == second["metadata"]["text_from"] == TEXT_FROM_LINES
    assert first["page_content"] == "Cold morning. Wrote letters\nuntil noon."
    assert second["page_content"] == "Rain all day. The convoy did not arrive."

    # A person corrects the last line: the day's entry reads the correction, without a re-run.
    _ok(client.post("/api/content-representations", json={
        "document_id": page["doc"].id, "segment_id": line[4], "kind": "transcription",
        "content": "Rain all day. The convoy came at dusk."}))
    first, second = _entries(client, page)
    assert second["page_content"] == "Rain all day. The convoy came at dusk."
    assert first["page_content"] == "Cold morning. Wrote letters\nuntil noon."
    assert _ok(client.get(f"/api/documents/{second['id']}"))["page_content"] == (
        "Rain all day. The convoy came at dusk.")

    # Run again: the same entries, matched, on the same lines; not doubled.
    again = await _split(test_package, page)
    assert again["created_count"] == 0 and again["removed_count"] == 0
    assert [(e["id"], e["metadata"]["lines"]) for e in _entries(client, page)] == [
        (first["id"], line[:3]), (second["id"], line[3:])]


@pytest.mark.asyncio
async def test_a_page_not_tied_keeps_the_copied_text_and_says_so_until_a_rerun_puts_it_on_lines(
        client, db, test_package, page, reader):
    """source.extract.entries-are-units, the first slice's "when not tied, keep today's behaviour and say
    the entry is not on lines". WHY: a diary split before its lines were tied still has its days; once
    tied, a re-run puts the same entries on their lines instead of making new ones."""
    await _split(test_package, page)
    first, second = _entries(client, page)
    assert first["metadata"]["lines"] == [] and first["metadata"]["text_from"] == NOT_TIED
    assert second["metadata"]["text_from"] == NOT_TIED
    assert first["page_content"] == "Cold morning. Wrote letters\nuntil noon."
    assert second["page_content"] == "Rain all day. The convoy did not arrive."

    _run(client, db, page)
    line = [row.id for row in _lines(db, page["kraken"].id)]
    again = await _split(test_package, page)
    assert again["created_count"] == 0 and again["updated_count"] == 2
    after = _entries(client, page)
    assert [e["id"] for e in after] == [first["id"], second["id"]]
    assert [e["metadata"]["lines"] for e in after] == [line[:3], line[3:]]
    assert {e["metadata"]["text_from"] for e in after} == {TEXT_FROM_LINES}
