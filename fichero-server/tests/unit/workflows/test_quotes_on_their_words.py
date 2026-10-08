"""`source.extract.quotes-on-their-words` (#5598): a quotation is a span on the quoted words, with its
speaker as a mention; the surrounding sentence is context, not the anchor.

Through the real paths: a page's lines imported from PAGE XML (`format.import`), its page reading tied to
those lines by the tie job (`POST /api/check/runs`, check `tie-text-to-lines`, Kraken faked at its seam as
in `tests/unit/check/test_tie_text_to_lines.py`), then Extract Quotes run as a workflow step runs it
(`_run_extractor` with the page as a record) with the model stubbed at `chat_structured_with_fallback`,
and everything read back through `GET /api/claims/{id}` and `GET /api/segments/{id}/statements`.

What breaks without these: a quotation highlighted on the whole sentence around it (so the speaker's
words and the narrator's run together), a quotation shown on no line, a speaker who is only a name in the
graph and never on the page, or a speaker made up from "X said" in the excerpt for a quotation the source
gives no speaker for.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from PIL import Image

from fichero_server.actions.registry import ActionContext, registry
from fichero_server.llm import LLMConfig
from fichero_server.models import Artifact, DocType, Document, FileType, Status
from fichero_server.models.knowledge import KnowledgeClaim
from fichero_server.models.segments import SegmentPass
from fichero_server.workflows.tools.extractors import _SECTION_SCHEMAS, _SECTIONS, _run_extractor
from tests.unit.check.test_tie_text_to_lines import _lines, _run, _tied, reader  # noqa: F401  (fixture)
from tests.unit.training.test_kraken_training_set import TEACHER

BOOT = ActionContext(actor="historian", library_path=None, is_bootstrap=True)
LINES = (
    "El alcalde Pedro Ruiz dijo",
    "«No daremos el agua a nadie», y se fue.",
    "Dicen en el pueblo que",
    "«el río es de todos los vecinos».",
)
SPEAKER, SAID = "Pedro Ruiz", "No daremos el agua a nadie"
UNSPOKEN = "el río es de todos los vecinos"


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
        f'<Page imageFilename="acta.jpg" imageWidth="{width}" imageHeight="{height}">'
        '<TextRegion id="r0" custom="readingOrder {index:0;}">'
        f'<Coords points="10,10 590,10 590,{height - 10} 10,{height - 10}"/>'
        + "".join(lines)
        + "</TextRegion></Page></PcGts>"
    )


@pytest.fixture
def page(db, tmp_path, jobs_run_by_the_test):
    """A page whose lines Kraken found, read whole by a model, and that reading tied to the lines."""
    folder = Document(name="Actas", doc_type=DocType.folder)
    db.save(folder)
    size = (600, 300)
    photo = tmp_path / "acta.jpg"
    Image.new("RGB", size, (220, 220, 210)).save(photo)
    doc = Document(name="acta.jpg", doc_type=DocType.file, file_type=FileType.image, path=str(photo),
                   parent_id=folder.id, status=Status.completed)
    db.save(doc)
    xml = tmp_path / "acta.xml"
    xml.write_text(_page_xml(*size), encoding="utf-8")
    registry.invoke(db, "format.import", {"document_id": doc.id, "path": str(xml)}, BOOT)
    (kraken,) = db.query(SegmentPass, document_id=doc.id)
    kraken.model = "kraken-blla"
    db.save(kraken)
    text = "\n".join(LINES)
    reading = Artifact(document_id=doc.id, artifact_type="transcription", content=text, model=TEACHER,
                       provider="openrouter")
    db.save(reading)
    return {"folder": folder, "doc": doc, "kraken": kraken, "text": text, "reading": reading}


def _ok(response):
    assert response.status_code == 200, response.text
    return response.json()


async def _extract(test_package, page, items):
    section = next(s for s in _SECTIONS if s["name"] == "quotes_extract")
    answer = _SECTION_SCHEMAS["quotes"](items=items)
    with patch("fichero_server.workflows.tools.extractors.chat_structured_with_fallback",
               new=AsyncMock(return_value=answer)):
        await _run_extractor(
            section,
            {"text": page["text"], "records": [{"doc_id": page["doc"].id, "text": page["text"]}]},
            {"library_path": str(test_package), "selected_doc_ids": [page["doc"].id], "task_id": "run-quotes"},
            LLMConfig(provider="openai", model="gpt-4o-mini"),
        )


def _claim(client, db, page, words):
    (row,) = [c for c in db.query(KnowledgeClaim, source_document_id=page["doc"].id) if c.object_phrase == words]
    return _ok(client.get(f"/api/claims/{row.id}"))


@pytest.mark.asyncio
async def test_a_quotation_is_anchored_on_its_words_on_its_line_and_its_speaker_is_a_mention(
        client, db, test_package, page, reader):
    """source.extract.quotes-on-their-words: "a quotation is a span on the quoted words themselves, with
    its speaker as a mention; the surrounding sentence is context, not the anchor".
    WHY: a reader following a quotation back to the page must land on the speaker's words, on the line
    they are written on, and see who said them where the page names him."""
    _job, status = _run(client, db, page)
    assert status["counts"]["tied"] == len(LINES)
    tied = dict((row.id, r) for row, r in _tied(db, page))
    line = [row.id for row in _lines(db, page["kraken"].id)]

    await _extract(test_package, page, [{
        "name": SPEAKER, "verb": "dijo", "object": f"«{SAID}»",
        # The model's sentence, joined across the line break as models give it.
        "source_text": f"El alcalde Pedro Ruiz dijo «{SAID}», y se fue.",
    }])

    claim = _claim(client, db, page, f"«{SAID}»")
    text = page["text"]
    # The anchor is the quoted words, exactly: not the sentence, not the quotation marks.
    assert text[claim["source_char_start"]:claim["source_char_end"]] == SAID
    assert claim["source_excerpt"] == SAID
    assert claim["metadata"]["quote_context"].startswith("El alcalde Pedro Ruiz dijo")
    # On the line the words are written on, measured on the reading the tie gave that line.
    anchor = claim["source_anchor"]
    assert anchor["segment_id"] == line[1]
    assert anchor["representation_id"] == tied[line[1]].id
    assert tied[line[1]].content[anchor["char_start"]:anchor["char_end"]] == SAID
    assert claim["metadata"]["quote_lines"] == [{
        "segment_id": line[1], "representation_id": tied[line[1]].id,
        "char_start": anchor["char_start"], "char_end": anchor["char_end"]}]
    assert claim["speaker_name"] == SPEAKER and claim["quotation_kind"] == "verbatim"

    # Read from the line: the quotation is on line 2 (by its anchor), the speaker a mention on line 1.
    on_quote_line = _ok(client.get(f"/api/segments/{line[1]}/statements"))
    assert [(c["claim_id"], c["via"]) for c in on_quote_line["claims"]] == [(claim["id"], "anchor")]
    assert on_quote_line["mentions"] == []
    on_speaker_line = _ok(client.get(f"/api/segments/{line[0]}/statements"))
    assert on_speaker_line["claims"] == []
    assert [(m["name"], m["excerpt"]) for m in on_speaker_line["mentions"]] == [(SPEAKER, SPEAKER)]
    start, end = claim["metadata"]["speaker_char_start"], claim["metadata"]["speaker_char_end"]
    assert text[start:end] == SPEAKER and claim["metadata"]["speaker_segment_id"] == line[0]


@pytest.mark.asyncio
async def test_an_unattributed_quotation_has_no_speaker_and_none_is_guessed(client, db, test_package, page, reader):
    """source.extract.quotes-on-their-words: the speaker is a mention "when one is identified; otherwise
    none". WHY: "Dicen en el pueblo" names nobody; a speaker read off the excerpt by an "X said" pattern
    would put words in a person's mouth the page never gives them."""
    _run(client, db, page)
    line = [row.id for row in _lines(db, page["kraken"].id)]
    await _extract(test_package, page, [{
        "name": None, "verb": "dicen", "object": UNSPOKEN,
        "source_text": f"Dicen en el pueblo que «{UNSPOKEN}».",
    }])

    claim = _claim(client, db, page, UNSPOKEN)
    assert page["text"][claim["source_char_start"]:claim["source_char_end"]] == UNSPOKEN
    assert claim["source_anchor"]["segment_id"] == line[3]
    assert claim["subject_canonical"] is None and claim["speaker_name"] is None
    assert claim["subject_entity_id"] is None
    said = _ok(client.get(f"/api/segments/{line[3]}/statements"))
    assert [c["claim_id"] for c in said["claims"]] == [claim["id"]] and said["mentions"] == []


@pytest.mark.asyncio
async def test_words_not_on_the_page_are_not_anchored_on_the_sentence(client, db, test_package, page, reader):
    """WHY: a quotation whose words the page does not hold is not evidence; anchoring it on the sentence
    instead (the old behaviour) would point a reader at words that are not the quotation. It is kept,
    unanchored, and says why."""
    _run(client, db, page)
    await _extract(test_package, page, [{
        "name": SPEAKER, "verb": "dijo", "object": "Entregaremos los papeles mañana",
        "source_text": f"El alcalde Pedro Ruiz dijo «{SAID}», y se fue.",
    }])

    claim = _claim(client, db, page, "Entregaremos los papeles mañana")
    assert claim["source_char_start"] is None and claim["source_char_end"] is None
    assert claim["source_anchor"] is None
    assert claim["metadata"]["quote_unanchored_reason"] == "the quoted words are not in the page text"
    assert "source_text" not in claim["metadata"]


@pytest.mark.asyncio
async def test_a_page_not_tied_to_lines_keeps_the_words_span_with_no_line(client, db, test_package, page):
    """WHY: before the tie (or on a page with no lines) the quotation still sits on its words in the page
    text; it names no line rather than a guessed one."""
    await _extract(test_package, page, [{
        "name": SPEAKER, "verb": "dijo", "object": SAID,
        "source_text": f"El alcalde Pedro Ruiz dijo «{SAID}», y se fue.",
    }])

    claim = _claim(client, db, page, SAID)
    assert page["text"][claim["source_char_start"]:claim["source_char_end"]] == SAID
    assert claim["source_anchor"] is None and "quote_lines" not in claim["metadata"]
    assert claim["metadata"]["speaker_char_start"] == page["text"].index(SPEAKER)
    assert "speaker_segment_id" not in claim["metadata"]
