"""Structured data, slice 1: a prototype's questions asked of its documents by a recipe step, each answer landing
as a typed attribute that cites its words (#5636), tested to the spec
(docs/contributor_manual/specs/source/structured-data.md, sections 1 and 2).

Behaviours: `structured.schema.question-wording`, `structured.extract.step-in-a-recipe`,
`structured.extract.text-first-then-image` (text half), `structured.extract.schema-constrained`,
`structured.extract.lands-on-attributes`, `structured.extract.not-found-is-a-status`,
`structured.cite.value-names-its-words`, `structured.cite.value-records-its-maker`.

Through the real paths: a page's lines imported from PAGE XML (`format.import`), so the page's text is derived from
its lines; the prototype made through `POST /api/classifications`; the Start plan (`plan_start`) and the recipe
runner (`runner.enqueue` + `runner.run`) running the `extract-to-a-table` card; a person's value set through
`PUT /api/documents/{id}`; everything read back through `GET /api/documents/{id}`. The model is stubbed at its
boundary only (`table.chat_structured_with_fallback`), answering per document from a fixed table.
"""
from __future__ import annotations

import pytest
from PIL import Image

from fichero_server.actions.registry import ActionContext, registry
from fichero_server.models import ContentRepresentation, DocType, Document, FileType, Status
from fichero_server.models.prototype_schema import AttributeDecl
from fichero_server.models.segments import Segment
from fichero_server.recipes import runner, table
from fichero_server.recipes.jobs import READING
from fichero_server.recipes.start import plan_start

BOOT = ActionContext(actor="historian", library_path=None, is_bootstrap=True)
DEEDS = {
    "deed-1.jpg": ("Sepan cuantos esta carta vieren", "como yo Juan Pérez vendo a Pedro Ruiz",
                   "una casa por cien ducados", "en Sevilla a 3 de marzo de 1795"),
    "deed-2.jpg": ("Sepan cuantos esta carta vieren", "como yo María López vendo a Antonio Gil",
                   "una viña por cuarenta ducados", "fecho en Carmona"),
}
SALE = {
    "seller": {"type": "text", "ask": "Who sells?", "examples": ["Juan de Ayala"]},
    "price": {"type": "number", "label": "Price in ducats"},
    "date": {"type": "date", "role": "date"},
}
#: What the model answers for each deed: per field (value, words, status, confidence).
ANSWERS = {
    "deed-1.jpg": {"seller": ("Juan Pérez", "Juan Pérez", "found", 0.9),
                   "price": ("100", "cien ducados", "found", 0.8),
                   "date": ("1795-03-03", "3 de marzo de 1795", "found", 0.7)},
    "deed-2.jpg": {"seller": ("María López", "María López", "found", 0.9),
                   "price": ("40", "cuarenta ducados", "found", 0.8),
                   "date": (None, None, "not_found", 0.6)},
}
MODEL = {"cloud": "openai", "model": "gpt-5"}
LINES = {"id": "lines", "job": "find-lines", "model": {"kraken": "blla", "kraken_version": "bundled"}}
READ = {"id": "read", "job": "read-a-line", "model": {"zenodo": "10.5281/zenodo.13788177"}}
TABLE = {"id": "table", "job": "extract-to-a-table", "model": MODEL, "runs_on": "cloud:openai",
         "settings": {"prototype": "sale"}}


def _page_xml(lines: tuple[str, ...]) -> str:
    rows = []
    for i, text in enumerate(lines):
        top = 20 + i * 60
        rows.append(
            f'<TextLine id="l{i}" custom="readingOrder {{index:{i};}}">'
            f'<Coords points="20,{top} 580,{top} 580,{top + 40} 20,{top + 40}"/>'
            f'<Baseline points="20,{top + 32} 580,{top + 32}"/>'
            f"<TextEquiv><Unicode>{text}</Unicode></TextEquiv></TextLine>")
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<PcGts xmlns="http://schema.primaresearch.org/PAGE/gts/pagecontent/2013-07-15">'
            "<Metadata><Creator>test</Creator><Created>2026-10-10T00:00:00</Created>"
            "<LastChange>2026-10-10T00:00:00</LastChange></Metadata>"
            '<Page imageFilename="deed.jpg" imageWidth="600" imageHeight="300">'
            '<TextRegion id="r0" custom="readingOrder {index:0;}">'
            '<Coords points="10,10 590,10 590,290 10,290"/>' + "".join(rows) + "</TextRegion></Page></PcGts>")


def _ok(response):
    assert response.status_code in (200, 201), response.text
    return response.json()


@pytest.fixture
def deeds(jobs_run_by_the_test, client, db, tmp_path):
    """Two deeds of the kind `sale`, each page's text derived from lines imported from PAGE XML, and a letter (no
    kind) beside them."""
    _ok(client.post("/api/classifications", json={"dimension": "document_prototype", "key": "sale", "label": "Sale",
                                                   "attributes": SALE}))
    folder = Document(name="Protocolo", doc_type=DocType.folder)
    db.save(folder)
    made = {}
    for name, lines in {**DEEDS, "letter.jpg": ("Querido hermano",)}.items():
        photo = tmp_path / name
        Image.new("RGB", (600, 300), (220, 220, 210)).save(photo)
        doc = Document(name=name, doc_type=DocType.file, file_type=FileType.image, path=str(photo),
                       parent_id=folder.id, status=Status.completed,
                       prototype_key="sale" if name in DEEDS else None)
        db.save(doc)
        xml = tmp_path / f"{name}.xml"
        xml.write_text(_page_xml(lines), encoding="utf-8")
        registry.invoke(db, "format.import", {"document_id": doc.id, "path": str(xml)}, BOOT)
        made[name] = db.get(Document, doc.id)
    return made


@pytest.fixture
def model(monkeypatch):
    """The model's answers, by the deed whose text it is given; every prompt it was given."""
    asked: list[dict] = []

    async def answer(prompt, schema, config, system=None, use_case=None, **kw):
        asked.append({"prompt": prompt, "schema": schema, "provider": config.provider, "model": config.model})
        name = next(n for n, lines in DEEDS.items() if lines[1] in prompt)
        return schema.model_validate({key: {"value": v, "words": w, "status": s, "confidence": c}
                                      for key, (v, w, s, c) in ANSWERS[name].items()})

    monkeypatch.setattr(table, "chat_structured_with_fallback", answer)
    return asked


def _run(db, documents, tmp_path, *steps):
    plan = plan_start({"fichero_recipe": 1, "id": "t/table", "version": "0.1.0", "title": "t",
                       "steps": list(steps or (LINES, READ, TABLE))}, stays_local=False)
    plan["runs"] = [r for r in plan["runs"] if r["card"] == "table"]
    job_id = runner.enqueue(db, plan, documents=documents, started_by="owner")
    _kind, subject = db.execute_fetchone("SELECT kind, subject FROM jobs WHERE id = ?", [job_id])
    (step,) = runner.run(db, subject)["steps"]
    return job_id, step


def _doc(client, doc_id):
    return _ok(client.get(f"/api/documents/{doc_id}"))


def _line(db, doc_id, words):
    """The segment whose reading holds `words`, and that reading."""
    for seg in db.query(Segment, document_id=doc_id):
        for rep in db.query(ContentRepresentation, segment_id=seg.id):
            if words in (rep.content or ""):
                return seg, rep
    raise AssertionError(f"no line of {doc_id} reads {words!r}")


# ── structured.schema.question-wording ──────────────────────────────────────────────────────────────


def test_a_field_carries_its_question_and_the_prompt_is_built_from_them():
    """structured.schema.question-wording: "each field carries the question a model is asked and a person reads, its
    label, and a few worded examples; the extraction prompt is built from them and nothing else". A field with no
    wording is asked from its label (or its key)."""
    seller = AttributeDecl.model_validate(SALE["seller"])
    price = AttributeDecl.model_validate(SALE["price"])
    date = AttributeDecl.model_validate(SALE["date"])
    assert seller.question("seller") == "Who sells?"
    assert price.question("price") == "What is the price in ducats?"
    assert date.question("date") == "What is the date?"
    fields = {"seller": seller, "price": price, "date": date}
    said = table.prompt(fields, "THE TEXT")
    assert "Who sells?" in said and "Example answer: Juan de Ayala" in said and "What is the price in ducats?" in said
    assert said.rstrip().endswith("THE TEXT")
    schema = table.answer_schema(fields).model_json_schema()
    assert set(schema["properties"]) == {"seller", "price", "date"}
    assert "Who sells?" in schema["properties"]["seller"]["description"]
    with pytest.raises(ValueError):
        AttributeDecl.model_validate({"type": "text", "asks": "a misspelt key is refused, never ignored"})


# ── the step and what it lands ──────────────────────────────────────────────────────────────────────


def test_the_step_is_a_card_that_takes_the_reading_and_names_its_prototype(tmp_path):
    """structured.extract.step-in-a-recipe: "Extract to a table" is a recipe step taking a prototype, after reading,
    with the step's own text model; one naming no prototype is skipped and says why."""
    plan = plan_start({"fichero_recipe": 1, "id": "t/t", "version": "0.1.0", "title": "t",
                       "steps": [LINES, READ, TABLE]}, stays_local=False)
    (card,) = [r for r in plan["runs"] if r["job"] == "extract-to-a-table"]
    assert card["card"] == "table" and card["prototype"] == "sale"
    assert (card["provider"], card["model"]) == ("openai", "gpt-5")
    assert card["takes"] == [READING] and card["gives"] == ["table_rows"]
    assert "table" not in {s["step"] for s in plan["skipped"]}

    bare = {**TABLE, "settings": {}}
    plan = plan_start({"fichero_recipe": 1, "id": "t/t", "version": "0.1.0", "title": "t",
                       "steps": [LINES, READ, bare]}, stays_local=False)
    (skip,) = [s for s in plan["skipped"] if s["step"] == "table"]
    assert "names no kind of document" in skip["why"]


def test_the_step_answers_each_document_of_the_prototype_and_lands_cited_values(
        client, db, deeds, model, tmp_path):
    """structured.extract.step-in-a-recipe, .schema-constrained, .lands-on-attributes, .text-first-then-image,
    structured.cite.value-names-its-words, .value-records-its-maker: the step asks one call per unit of the
    prototype (the letter, of no kind, is not asked), with the unit's derived text; each answer lands as the node's
    typed attribute through the attribute write path, its source the run, the model, its answer, the status and the
    words, on the line they are written on."""
    job_id, step = _run(db, [d.id for d in deeds.values()], tmp_path)
    assert step["state"] == "done", step
    assert step["table"] == {"prototype": "sale", "units": 2, "asked": 2, "without_text": 0, "values": 5,
                             "not_found": 1, "refused": 0, "kept": 0, "unanchored": 0, "failed": 0}
    assert len(model) == 2 and {(m["provider"], m["model"]) for m in model} == {("openai", "gpt-5")}
    first = deeds["deed-1.jpg"]
    (prompt,) = [m["prompt"] for m in model if DEEDS["deed-1.jpg"][1] in m["prompt"]]
    assert first.page_content and first.page_content in prompt  # the derived text, whole

    doc = _doc(client, first.id)
    assert {k: doc["attributes"][k] for k in SALE} == {"seller": "Juan Pérez", "price": 100, "date": "1795-03-03"}
    source = doc["metadata"]["attribute_sources"]["seller"]
    assert source["by"] == "machine" and source["tool"] == "extract-to-a-table" and source["step"] == "table"
    assert (source["provider"], source["model"], source["run_id"]) == ("openai", "gpt-5", job_id)
    assert source["status"] == "found" and source["confidence_said"] == 0.9 and "Juan Pérez" in source["said"]
    assert source["method"] and source["input"]["cer"] is None  # the reading's error rate is not measured yet
    seg, rep = _line(db, first.id, "Juan Pérez")
    cites = source["cites"]
    assert (cites["anchor"], cites["words"], cites["document_id"]) == ("exact", "Juan Pérez", first.id)
    assert (cites["segment_id"], cites["representation_id"]) == (seg.id, rep.id)
    assert rep.content[cites["line_char_start"]:cites["line_char_end"]] == "Juan Pérez"
    assert first.page_content[cites["char_start"]:cites["char_end"]] == "Juan Pérez"
    price = doc["metadata"]["attribute_sources"]["price"]["cites"]
    assert price["words"] == "cien ducados" and price["segment_id"] == _line(db, first.id, "cien ducados")[0].id

    letter = _doc(client, deeds["letter.jpg"].id)
    assert not (letter["metadata"] or {}).get("attribute_sources") and not set(SALE) & set(letter["attributes"] or {})


def test_not_found_is_a_status_with_no_value(client, db, deeds, model, tmp_path):
    """structured.extract.not-found-is-a-status: "not found, illegible and ambiguous are statuses on the value,
    distinct from an empty value and from a field nobody filled" -- the second deed gives no date: the date has a
    source saying not_found, and no value, never a guess."""
    _run(db, [deeds["deed-2.jpg"].id], tmp_path)
    doc = _doc(client, deeds["deed-2.jpg"].id)
    assert "date" not in doc["attributes"]
    source = doc["metadata"]["attribute_sources"]["date"]
    assert source["status"] == "not_found" and source["by"] == "machine" and source["cites"] is None
    assert doc["attributes"]["seller"] == "María López"


def test_a_type_invalid_answer_is_refused_for_its_field_only(client, db, deeds, model, monkeypatch, tmp_path):
    """structured.extract.schema-constrained: the answer is validated against the field types; an answer of the
    wrong type is refused for that field, named on the step's account with why, and the unit's other answers land."""
    monkeypatch.setitem(ANSWERS, "deed-1.jpg", {**ANSWERS["deed-1.jpg"],
                                                "price": ("cien", "cien ducados", "found", 0.8)})
    _job, step = _run(db, [deeds["deed-1.jpg"].id], tmp_path)
    assert step["state"] == "done" and step["table"]["refused"] == 1 and step["table"]["values"] == 2
    (refusal,) = step["table_refusals"]
    assert (refusal["field"], refusal["said"], refusal["document_id"]) == ("price", "cien", deeds["deed-1.jpg"].id)
    assert "not a number" in refusal["why"]
    doc = _doc(client, deeds["deed-1.jpg"].id)
    assert "price" not in doc["attributes"] and "price" not in doc["metadata"]["attribute_sources"]
    assert doc["attributes"]["seller"] == "Juan Pérez" and doc["attributes"]["date"] == "1795-03-03"


def test_a_persons_value_is_never_overwritten(client, db, deeds, model, tmp_path):
    """structured.extract.lands-on-attributes: "a person's value is never overwritten" -- the seller a person typed
    stands, cites nothing, and the step counts it as kept."""
    first = deeds["deed-1.jpg"]
    _ok(client.put(f"/api/documents/{first.id}", json={"attributes": {"seller": "Juan Pérez de Guzmán"}}))
    _job, step = _run(db, [first.id], tmp_path)
    assert step["table"]["kept"] == 1 and step["table"]["values"] == 2
    doc = _doc(client, first.id)
    assert doc["attributes"]["seller"] == "Juan Pérez de Guzmán"
    assert doc["metadata"]["attribute_sources"]["seller"] == {"by": "person"}
    assert doc["attributes"]["price"] == 100


def test_words_not_written_exactly_are_found_fuzzy_or_kept_unanchored(client, db, deeds, model, monkeypatch,
                                                                      tmp_path):
    """structured.cite.value-names-its-words: words "found exactly or by the closest real span (labelled fuzzy); a
    value whose words are not on the page is kept with `anchor: none` and a reason"."""
    monkeypatch.setitem(ANSWERS, "deed-1.jpg", {
        "seller": ("Juan Pérez", "yo Juan Peres vendo", "found", 0.9),       # a slip of the model's: fuzzy
        "price": ("100", "ciento veinte ducados", "found", 0.8),             # not on the page
        "date": ("1795-03-03", "3 de marzo de 1795", "found", 0.7)})
    _job, step = _run(db, [deeds["deed-1.jpg"].id], tmp_path)
    assert step["table"]["values"] == 3 and step["table"]["unanchored"] == 1
    sources = _doc(client, deeds["deed-1.jpg"].id)["metadata"]["attribute_sources"]
    seller = sources["seller"]["cites"]
    assert seller["anchor"] == "fuzzy" and seller["model_words"] == "yo Juan Peres vendo"
    assert "Juan Pérez" in seller["words"] and seller["segment_id"] == _line(db, deeds["deed-1.jpg"].id,
                                                                              "Juan Pérez")[0].id
    price = sources["price"]["cites"]
    assert price["anchor"] == "none" and price["reason"] == "the words are not in the text"
    assert price["segment_id"] is None and price["words"] == "ciento veinte ducados"


def test_entries_of_the_prototype_are_units_cited_on_their_pages_lines(client, db, deeds, model, tmp_path):
    """structured.extract.step-in-a-recipe: the units are "the documents/entries of a chosen prototype" -- an entry
    under a page of no kind is asked from its own text, and its words are cited on its page's line."""
    from fichero_server.workflows.tools.diary_entries import _DIARY_TOOL_KEY

    letter = deeds["letter.jpg"]
    second = deeds["deed-2.jpg"]
    seg, rep = _line(db, second.id, "María López")
    # the second deed's sale, as an entry of the letter's page would carry it: its own text, and its line
    entry = Document(parent_id=second.id, doc_type=DocType.file, node_kind="entry", name="Entry 1", sequence=1,
                     status=Status.completed, prototype_key="sale", page_content=rep.content,
                     metadata={_DIARY_TOOL_KEY: True, "lines": [seg.id]})
    db.save(entry)
    second.prototype_key = None
    db.save(second)
    _job, step = _run(db, [letter.id, second.id], tmp_path)
    assert step["table"]["units"] == 1 and step["table"]["asked"] == 1, step["table"]
    doc = _doc(client, entry.id)
    assert doc["attributes"]["seller"] == "María López"
    cites = doc["metadata"]["attribute_sources"]["seller"]["cites"]
    assert (cites["document_id"], cites["segment_id"], cites["anchor"]) == (second.id, seg.id, "exact")
