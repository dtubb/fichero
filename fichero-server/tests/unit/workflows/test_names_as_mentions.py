"""`source.extract.names-as-mentions` (#5488) and `source.extract.statements-on-segments` (#4932): a name
found is a mention (a segment, a reading and a character span, joined to its entity), and a statement whose
words are on the page rests on the line they start on.

Through the real paths: a page's lines imported from PAGE XML (`format.import`), its page reading tied to
those lines by the tie job (`POST /api/check/runs`, Kraken faked at its seam as in
`tests/unit/check/test_tie_text_to_lines.py`), then Extract Entities (`extract_entities_only`) run with a
language model stubbed at `chat_structured_with_fallback`, or with spaCy whose pipeline is a stub returning
`doc.ents` (so `spacy_ner.extract_entities` and `SpacyNERProvider` run for real), and Extract People
(`_run_extractor`); everything read back through `GET /api/segments/{id}/statements`,
`GET /api/entities/{id}` and `GET /api/claims/{id}`.

What breaks without these: a name that is only "somewhere in this document" (spaCy's spans computed and
thrown away), a line whose "what is said here" is empty although the page names a person on it, and a
model's name placed on a page that does not write it.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from PIL import Image

from fichero_server.actions.registry import ActionContext, registry
from fichero_server.knowledge import spacy_ner
from fichero_server.llm import LLMConfig
from fichero_server.models import Artifact, DocType, Document, FileType, Status
from fichero_server.models.knowledge import KnowledgeClaim, KnowledgeEntity
from fichero_server.models.segments import SegmentPass
from fichero_server.workflows.tools.extract_all import _EntitiesOnly, _EntityOnly
from fichero_server.workflows.tools.extract_entities_only import extract_entities_only
from fichero_server.workflows.tools.extractors import _SECTION_SCHEMAS, _SECTIONS, _run_extractor
from tests.unit.check.test_tie_text_to_lines import _lines, _run, _tied, reader  # noqa: F401  (fixture)
from tests.unit.training.test_kraken_training_set import TEACHER

BOOT = ActionContext(actor="historian", library_path=None, is_bootstrap=True)
LINES = (
    "Pedro Ruiz vecino de Quibdó dijo",
    "que el río era de todos. Ruiz",
    "firmó ante Juan de Mena.",
)


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
    """A page whose lines Kraken found, read whole by a model (the page's only text)."""
    folder = Document(name="Actas", doc_type=DocType.folder)
    db.save(folder)
    size = (600, 240)
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
    doc = db.get(Document, doc.id)
    doc.page_content = text  # what Extract Entities reads, the same words the reading holds
    db.save(doc)
    reading = Artifact(document_id=doc.id, artifact_type="transcription", content=text, model=TEACHER,
                       provider="openrouter")
    db.save(reading)
    return {"folder": folder, "doc": doc, "kraken": kraken, "text": text, "reading": reading}


def _ok(response):
    assert response.status_code == 200, response.text
    return response.json()


async def _entities(test_package, page, llm_config, answer=None):
    patcher = patch("fichero_server.workflows.tools.extract_entities_only.chat_structured_with_fallback",
                    new=AsyncMock(return_value=answer))
    with patcher:
        return await extract_entities_only(
            {"documents": [{"id": page["doc"].id}]},
            {"library_path": str(test_package), "selected_doc_ids": [page["doc"].id], "task_id": "run-names"},
            llm_config,
        )


def _entity(client, db, name):
    (row,) = [e for e in db.query(KnowledgeEntity) if e.canonical_name == name]
    return _ok(client.get(f"/api/entities/{row.id}"))


def _mentions(client, segment_id):
    return sorted((m["name"], m["excerpt"]) for m in _ok(client.get(f"/api/segments/{segment_id}/statements"))["mentions"])


class _Ents:
    """spaCy's pipeline, stubbed at the model: each listed surface form is an entity at every place the
    text writes it, as a real `doc.ents` would be."""

    def __init__(self, found):
        self.found = found

    def __call__(self, text):
        ents = []
        for surface, label in self.found:
            at = text.find(surface)
            while at >= 0:
                end = at + len(surface)
                # spaCy's entities never overlap: the first listed (the longer) keeps the words.
                if not any(at < e.end_char and e.start_char < end for e in ents):
                    ents.append(SimpleNamespace(text=surface, label_=label, start_char=at, end_char=end))
                at = text.find(surface, at + 1)
        return SimpleNamespace(ents=sorted(ents, key=lambda e: e.start_char))


@pytest.mark.asyncio
async def test_a_models_names_are_mentions_on_their_lines_and_an_unwritten_one_says_so(
        client, db, test_package, page, reader):
    """source.extract.names-as-mentions: "a model's name is found in the reading and tied the same way, and
    an unfound name is kept as unanchored and says so". WHY: from a line, the reader asks who is named on
    it; from a person, where the page names him. A name the page does not write is not put on a line."""
    _job, status = _run(client, db, page)
    assert status["counts"]["tied"] == len(LINES)
    tied = dict((row.id, r) for row, r in _tied(db, page))
    line = [row.id for row in _lines(db, page["kraken"].id)]

    result = await _entities(test_package, page, LLMConfig(provider="openai", model="gpt-4o-mini"), _EntitiesOnly(
        people=[_EntityOnly(name="Pedro Ruiz", aliases=["Ruiz"]), _EntityOnly(name="Juan de Mena", aliases=[]),
                _EntityOnly(name="Antonio Guzmán", aliases=[])],
        places=[_EntityOnly(name="Quibdó", aliases=[])]))
    assert result["summary"]["mentions_on_lines"] == 4

    assert _mentions(client, line[0]) == [("Pedro Ruiz", "Pedro Ruiz"), ("Quibdó", "Quibdó")]
    assert _mentions(client, line[1]) == [("Pedro Ruiz", "Ruiz")]
    assert _mentions(client, line[2]) == [("Juan de Mena", "Juan de Mena")]

    # From the entity: each place, its span in the page text, its line and the reading the tie gave it.
    pedro = _entity(client, db, "Pedro Ruiz")
    text = page["text"]
    spans = [(s["source_char_start"], s["source_char_end"]) for s in pedro["source_supports"]]
    assert [text[a:b] for a, b in spans] == ["Pedro Ruiz", "Ruiz"]
    for support in pedro["source_supports"]:
        anchor = support["source_anchor"]
        assert anchor["representation_id"] == tied[anchor["segment_id"]].id
        assert tied[anchor["segment_id"]].content[anchor["char_start"]:anchor["char_end"]] == support["source_excerpt"]

    (unwritten,) = _entity(client, db, "Antonio Guzmán")["source_supports"]
    assert unwritten["source_char_start"] is None and unwritten["source_anchor"] is None
    assert unwritten["mention_unanchored_reason"] == "the name is not written in the page text"

    # Run again: the same mentions, not doubled.
    await _entities(test_package, page, LLMConfig(provider="openai", model="gpt-4o-mini"), _EntitiesOnly(
        people=[_EntityOnly(name="Pedro Ruiz", aliases=["Ruiz"])]))
    assert len(_entity(client, db, "Pedro Ruiz")["source_supports"]) == 2


@pytest.mark.asyncio
async def test_spacys_spans_are_kept_every_one_on_its_line(client, db, test_package, page, reader, monkeypatch):
    """source.extract.names-as-mentions: "a spaCy span is kept". WHY: spaCy says exactly where it read each
    name; that was computed and discarded, leaving the entity tied to the document only."""
    _run(client, db, page)
    line = [row.id for row in _lines(db, page["kraken"].id)]
    nlp = _Ents([("Pedro Ruiz vecino de Quibdó", "PER"), ("Ruiz", "PER"), ("Quibdó", "LOC"),
                 ("Juan de Mena", "PER")])
    monkeypatch.setattr(spacy_ner, "_load_pipeline", lambda lang: nlp)

    result = await _entities(test_package, page, LLMConfig(provider="spacy", model=""))
    # The person's span stops at the name (spaCy's ran on into "vecino de Quibdó", so Quibdó is not an
    # entity of its own there); the alias "Ruiz" on line 2 is the same person's mention there.
    assert result["summary"]["mentions_on_lines"] == 3
    assert _mentions(client, line[0]) == [("Pedro Ruiz", "Pedro Ruiz")]
    assert _mentions(client, line[1]) == [("Pedro Ruiz", "Ruiz")]
    assert _mentions(client, line[2]) == [("Juan de Mena", "Juan de Mena")]


@pytest.mark.asyncio
async def test_a_page_not_tied_keeps_the_span_and_names_its_line_once_tied(client, db, test_package, page, reader):
    """source.extract.names-as-mentions, and slice 2's "when the page isn't tied, keep the text span without
    a line". WHY: a name read before the lines were tied is still a place on the page; once tied, a rerun
    names its line instead of adding a second mention."""
    llm = LLMConfig(provider="openai", model="gpt-4o-mini")
    answer = _EntitiesOnly(people=[_EntityOnly(name="Juan de Mena", aliases=[])])
    await _entities(test_package, page, llm, answer)
    (support,) = _entity(client, db, "Juan de Mena")["source_supports"]
    assert page["text"][support["source_char_start"]:support["source_char_end"]] == "Juan de Mena"
    assert support["source_anchor"] is None

    _run(client, db, page)
    line = [row.id for row in _lines(db, page["kraken"].id)]
    await _entities(test_package, page, llm, answer)
    (support,) = _entity(client, db, "Juan de Mena")["source_supports"]
    assert support["source_anchor"]["segment_id"] == line[2]
    assert _mentions(client, line[2]) == [("Juan de Mena", "Juan de Mena")]


@pytest.mark.asyncio
async def test_a_statement_rests_on_the_line_its_words_start_on(client, db, test_package, page, reader):
    """source.extract.statements-on-segments: "an extractor filling `segment_id` and `representation_id`
    on the claim's anchor", and the section extractors' names as mentions. WHY: the line's statements
    section was empty for every extracted claim, since none named a segment."""
    _run(client, db, page)
    tied = dict((row.id, r) for row, r in _tied(db, page))
    line = [row.id for row in _lines(db, page["kraken"].id)]
    section = next(s for s in _SECTIONS if s["name"] == "people_extract")
    answer = _SECTION_SCHEMAS[section["schema_key"]](items=[{
        "name": "Juan de Mena", "verb": "witnessed", "object": "the signature",
        "source_text": "firmó ante Juan de Mena."}])
    with patch("fichero_server.workflows.tools.extractors.chat_structured_with_fallback",
               new=AsyncMock(return_value=answer)):
        await _run_extractor(
            section,
            {"text": page["text"], "records": [{"doc_id": page["doc"].id, "text": page["text"]}]},
            {"library_path": str(test_package), "selected_doc_ids": [page["doc"].id], "task_id": "run-people"},
            LLMConfig(provider="openai", model="gpt-4o-mini"),
        )

    (row,) = [c for c in db.query(KnowledgeClaim, source_document_id=page["doc"].id)
              if c.subject_canonical == "Juan de Mena"]
    claim = _ok(client.get(f"/api/claims/{row.id}"))
    anchor = claim["source_anchor"]
    assert anchor["segment_id"] == line[2] and anchor["representation_id"] == tied[line[2]].id
    assert tied[line[2]].content[anchor["char_start"]:anchor["char_end"]] == "firmó ante Juan de Mena."
    said = _ok(client.get(f"/api/segments/{line[2]}/statements"))
    assert [(c["claim_id"], c["via"]) for c in said["claims"]] == [(row.id, "anchor")]
    assert [(m["name"], m["excerpt"]) for m in said["mentions"]] == [("Juan de Mena", "Juan de Mena")]
