"""`source.extract.exported` (#5603): the export reads the one record.

The record stream (`iter_export_records`, written as Parquet by `POST /api/export/parquet`) carries a
document's date, prototype, attribute values with who set them and its own readings by kind, every mention
with its span and line, and every claim with its anchor; TEI (`GET /api/documents/{id}/export/tei`) writes
the names and dates inline at their spans in the lines; the W3C annotation page
(`GET /api/documents/{id}/annotations.jsonld`) writes a machine's mentions and statements with segment and
text selectors and the run that made them.

The library is built through the real seams: the page's lines imported from PAGE XML (`format.import`), the
mentions written by the mention writer (`extractors.write_mentions`) and the quotation anchored by the
anchor writer (`extractors.line_anchor`), over the line spans the tie hands them (`tie_text.LineSpan`, here
built from the imported lines' own readings, which is what a tie of the same text gives).

What breaks without this: an export in which a person is "somewhere in this document", a TEI edition with
no names in it although the library knows where each is written, and an annotation page that shows only
a person's own marks.
"""
from __future__ import annotations

import json

import duckdb
import pytest
from lxml import etree
from PIL import Image

from fichero_server.actions.registry import ActionContext, registry
from fichero_server.api.routes.document.segment_readings import ordered_lines, readings_of_segment
from fichero_server.checking.tie_text import LineSpan
from fichero_server.models import ContentRepresentation, DocType, Document, FileType, Status
from fichero_server.models.anchors import SourceAnchor
from fichero_server.models.knowledge import (
    ClaimType,
    EntityType,
    KnowledgeClaim,
    KnowledgeEntity,
    QuotationKind,
)
from fichero_server.models.segments import SegmentPass
from fichero_server.workflows.attribute_sources import machine_source, with_sources
from fichero_server.workflows.tools._entity_writer import run_attribution
from fichero_server.workflows.tools.extractors import line_anchor, write_mentions

BOOT = ActionContext(actor="historian", library_path=None, is_bootstrap=True)
TEI = "{http://www.tei-c.org/ns/1.0}"
LINES = (
    "En Quibdó a 3 de mayo de 1790",
    "Pedro Ruiz dijo que el río era de todos",
    "y firmó ante el alcalde.",
)
TEXT = "\n".join(LINES)
RUN = "run-names-7"


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


def _span(word: str) -> tuple[int, int]:
    at = TEXT.index(word)
    return at, at + len(word)


@pytest.fixture
def library(db, tmp_path):
    folder = Document(name="Actas", doc_type=DocType.folder)
    db.save(folder)
    photo = tmp_path / "acta.jpg"
    Image.new("RGB", (600, 240), (220, 220, 210)).save(photo)
    doc = Document(name="acta.jpg", doc_type=DocType.file, file_type=FileType.image, path=str(photo),
                   parent_id=folder.id, status=Status.completed)
    db.save(doc)
    xml = tmp_path / "acta.xml"
    xml.write_text(_page_xml(600, 240), encoding="utf-8")
    registry.invoke(db, "format.import", {"document_id": doc.id, "path": str(xml)}, BOOT)
    (page_pass,) = db.query(SegmentPass, document_id=doc.id)

    # The line spans a tie of this text gives: each line, its reading, its stretch of the page text.
    lines, offset = [], 0
    for row, text in zip(ordered_lines(db, page_pass.id), LINES):
        (reading,) = [r for r in readings_of_segment(db, row.id) if r.kind == "transcription"]
        assert reading.content == text
        lines.append(LineSpan(row.id, reading.id, offset, offset + len(text)))
        offset += len(text) + 1

    doc = db.get(Document, doc.id)
    doc.page_content = TEXT
    # The page's date where it lives (`work-out-dates`), its kind and an attribute a run set, citing it.
    doc.date_original = "3 de mayo de 1790"
    doc.date_jdn = doc.date_jdn_end = 2375000
    doc.date_meta = {"status": "dated", "display": "3 May 1790", "precision": "day", "source": "extracted"}
    doc.prototype_key = "Acta"
    doc.attributes = {"scene": "a notary's office"}
    doc.metadata = with_sources(doc.metadata, {
        "scene": machine_source(tool="scene", run_id="run-scene-1", artifact_id="art-1", provider="openrouter",
                                model="vision-model", said="a notary's office"),
        "prototype": {"by": "person"},
    })
    db.save(doc)
    # A description of the whole page (#5599): a reading of its kind, not an artifact.
    db.save(ContentRepresentation(document_id=doc.id, kind="description", content="An act signed at Quibdó.",
                                  source_anchor=SourceAnchor(document_id=doc.id), producer_tool="describe",
                                  producer_run_id="run-describe-1", producer_model="vision-model"))

    # Names, written by the mention writer on the lines they stand on; one the page does not write.
    made = run_attribution("openrouter", "names-model", RUN)
    pedro = KnowledgeEntity(canonical_name="Pedro Ruiz", entity_type=EntityType.person)
    pedro.add_attribution(made)
    quibdo = KnowledgeEntity(canonical_name="Quibdó", entity_type=EntityType.location)
    quibdo.add_attribution(made)
    mena = KnowledgeEntity(canonical_name="Juan de Mena", entity_type=EntityType.person)
    mena.add_attribution(made)
    for entity in (pedro, quibdo, mena):
        db.save(entity)
    write_mentions(db, pedro.id, doc.id, TEXT, [_span("Pedro Ruiz")], lines, name="Pedro Ruiz")
    write_mentions(db, quibdo.id, doc.id, TEXT, [_span("Quibdó")], lines, name="Quibdó")
    write_mentions(db, mena.id, doc.id, TEXT, [], lines, name="Juan de Mena")

    # A quotation on its own words, and a date stated in its sentence, each on the line it starts on.
    q_start, q_end = _span("el río era de todos")
    quote = KnowledgeClaim(
        text="Pedro Ruiz: el río era de todos", source_document_id=doc.id, claim_type=ClaimType.fact,
        source_char_start=q_start, source_char_end=q_end, quotation_kind=QuotationKind.verbatim,
        speaker_entity_id=pedro.id, entity_ids=[pedro.id], provider="openrouter", model="quotes-model",
        source_anchor=line_anchor(lines, doc.id, q_start, q_end),
        metadata={"quote_text": "el río era de todos", "source_text": "el río era de todos"},
    )
    d_start, d_end = 0, len(LINES[0])
    dated = KnowledgeClaim(
        text="1790-05-03: act signed", source_document_id=doc.id, claim_type=ClaimType.fact,
        source_char_start=d_start, source_char_end=d_end, time_start="1790-05-03", provider="openrouter",
        model="dates-model", source_anchor=line_anchor(lines, doc.id, d_start, d_end),
        metadata={"date_text": "3 de mayo de 1790", "date_normalized": "1790-05-03", "source_text": LINES[0]},
    )
    db.save(quote)
    db.save(dated)
    return {"doc": doc, "folder": folder, "lines": lines, "pedro": pedro, "quibdo": quibdo, "mena": mena,
            "quote": quote, "dated": dated}


def _ok(response):
    assert response.status_code == 200, response.text
    return response.json()


def _rows(path, sql="SELECT * FROM read_parquet(?)"):
    with duckdb.connect() as connection:
        cursor = connection.execute(sql, [str(path)])
        names = [d[0] for d in cursor.description]
        return [dict(zip(names, row)) for row in cursor.fetchall()]


def test_the_record_stream_carries_dates_attributes_readings_mentions_and_anchors(client, library, tmp_path):
    """The Parquet a person exports through the route holds what the library knows of the page: its date,
    kind, attribute values with who set them and its description; each name on its line with its span;
    each claim on its line with the span in that line's reading."""
    doc, lines = library["doc"], library["lines"]
    out = tmp_path / "bundle"
    body = _ok(client.post("/api/export/parquet", json={"output_path": str(out), "target_id": library["folder"].id}))
    assert str(out / "mentions.parquet") in body["files"]
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["files"]["mentions"]["record_count"] == 3

    (page,) = [r for r in _rows(out / "documents.parquet") if r["document_id"] == doc.id]
    assert (page["date_original"], page["date_jdn"], page["date_status"], page["date_display"]) == (
        "3 de mayo de 1790", 2375000, "dated", "3 May 1790")
    assert page["prototype"] == "Acta"
    values = {v["key"]: v for v in page["attribute_values"]}
    assert values["scene"]["value"] == "a notary's office"
    assert (values["scene"]["by"], values["scene"]["tool"], values["scene"]["run_id"]) == (
        "machine", "scene", "run-scene-1")
    assert (values["prototype"]["value"], values["prototype"]["by"]) == ("Acta", "person")
    (description,) = page["readings"]
    assert (description["kind"], description["content"], description["producer_run_id"]) == (
        "description", "An act signed at Quibdó.", "run-describe-1")

    mentions = {m["canonical_name"]: m for m in _rows(out / "mentions.parquet")}
    pedro = mentions["Pedro Ruiz"]
    start, end = _span("Pedro Ruiz")
    assert (pedro["char_start"], pedro["char_end"]) == (start, end)
    assert (pedro["segment_id"], pedro["reading_id"]) == (lines[1].segment_id, lines[1].representation_id)
    assert (pedro["segment_char_start"], pedro["segment_char_end"]) == (0, len("Pedro Ruiz"))
    assert (pedro["made_by"]["by"], pedro["made_by"]["run_id"]) == ("machine", RUN)
    quibdo = mentions["Quibdó"]
    assert (quibdo["segment_id"], quibdo["segment_char_start"]) == (lines[0].segment_id, 3)
    mena = mentions["Juan de Mena"]
    assert mena["char_start"] is None and mena["segment_id"] is None and mena["unanchored_reason"]

    claims = {c["claim_id"]: c for c in _rows(out / "claims.parquet")}
    quote = claims[library["quote"].id]
    assert (quote["segment_id"], quote["reading_id"]) == (lines[1].segment_id, lines[1].representation_id)
    assert LINES[1][quote["segment_char_start"]:quote["segment_char_end"]] == "el río era de todos"
    assert (quote["quotation_kind"], quote["speaker_entity_id"]) == ("verbatim", library["pedro"].id)
    dated = claims[library["dated"].id]
    assert (dated["date_text"], str(dated["date_normalized"]), dated["segment_id"]) == (
        "3 de mayo de 1790", "1790-05-03", lines[0].segment_id)


def test_tei_writes_names_and_dates_inline_at_their_spans_and_leaves_the_text_alone(client, library):
    """Each name is its element at the words that write it, pointing at its entity; a date is `<date
    when>` on its words; every line still reads exactly as it did."""
    body = _ok(client.get(f"/api/documents/{library['doc'].id}/export/tei"))
    root = etree.fromstring(body["content"].encode("utf-8"))

    (pers,) = root.iter(f"{TEI}persName")
    assert pers.text == "Pedro Ruiz"
    assert pers.get("ref") == f"fichero:entity:{library['pedro'].id}"
    (place,) = root.iter(f"{TEI}placeName")
    assert (place.text, place.get("ref")) == ("Quibdó", f"fichero:entity:{library['quibdo'].id}")
    (date,) = root.iter(f"{TEI}date")
    assert (date.text, date.get("when")) == ("3 de mayo de 1790", "1790-05-03")
    # The unanchored name is not put anywhere.
    assert "Juan de Mena" not in body["content"]

    # The text is untouched: the region's words, read through the new elements, are the page's lines.
    (ab,) = [a for a in root.iter(f"{TEI}ab")]
    text = "".join(ab.itertext())
    for line in LINES:
        assert line in text
    # The name sits on its line: the placeName comes after the first <lb>, before the second.
    tags = [el.tag.replace(TEI, "") for el in ab.iter() if el.tag in (f"{TEI}lb", f"{TEI}placeName",
                                                                        f"{TEI}date", f"{TEI}persName")]
    assert tags == ["lb", "placeName", "date", "lb", "persName", "lb"]


def test_w3c_annotations_carry_machine_mentions_and_statements_with_selectors_and_the_run(client, library):
    """A name the run found is an `identifying` annotation on its line with the span in that line's reading
    and the quoted words; a statement is `describing` on its words; each names the run, not a person."""
    lines = library["lines"]
    page = _ok(client.get(f"/api/documents/{library['doc'].id}/annotations.jsonld"))
    identifying = {a["body"]["label"]: a for a in page["items"] if a["motivation"] == "identifying"}
    assert set(identifying) == {"Pedro Ruiz", "Quibdó"}, "the unanchored name has nowhere to point"
    pedro = identifying["Pedro Ruiz"]
    assert pedro["body"]["source"] == f"/api/entities/{library['pedro'].id}"
    assert pedro["target"]["source"] == f"/api/segments/{lines[1].segment_id}"
    assert pedro["target"]["reading"] == f"/api/content-representations/{lines[1].representation_id}"
    assert pedro["target"]["selector"] == [
        {"type": "TextPositionSelector", "start": 0, "end": len("Pedro Ruiz")},
        {"type": "TextQuoteSelector", "exact": "Pedro Ruiz"},
    ]
    assert pedro["creator"] == {"type": "Software", "name": "names-model", "id": f"fichero:run:{RUN}",
                                "nickname": "openrouter"}

    describing = {a["id"].rsplit("/", 1)[-1]: a for a in page["items"] if a["motivation"] == "describing"}
    quote = describing[library["quote"].id]
    assert quote["target"]["source"] == f"/api/segments/{lines[1].segment_id}"
    position, exact = quote["target"]["selector"]
    assert LINES[1][position["start"]:position["end"]] == "el río era de todos" == exact["exact"]
    assert quote["creator"]["type"] == "Software" and quote["creator"]["name"] == "quotes-model"
    dated = describing[library["dated"].id]
    assert {"type": "TextualBody", "purpose": "tagging", "format": "text/plain", "value": "1790-05-03"} in dated["body"]


def test_on_a_page_with_no_lines_a_mention_points_at_the_words_in_the_page_text(client, db, library):
    """A page with no lines keeps its names on the page text: the annotation targets the page with the
    words and their place in the text; no line is guessed."""
    page = Document(name="carta.txt", doc_type=DocType.file, file_type=FileType.text,
                    page_content="Carta de Pedro Ruiz al cabildo.")
    db.save(page)
    at = page.page_content.index("Pedro Ruiz")
    write_mentions(db, library["pedro"].id, page.id, page.page_content, [(at, at + len("Pedro Ruiz"))], [],
                   name="Pedro Ruiz")
    items = _ok(client.get(f"/api/documents/{page.id}/annotations.jsonld"))["items"]
    (mention,) = [a for a in items if a["motivation"] == "identifying"]
    assert mention["target"]["source"].endswith("/canvas/1")
    assert mention["target"]["selector"] == [
        {"type": "TextQuoteSelector", "exact": "Pedro Ruiz"},
        {"type": "TextPositionSelector", "start": at, "end": at + len("Pedro Ruiz")},
    ]
