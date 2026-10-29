"""The names and statements steps use the quality rules: each test fails when its call is taken out (synthetic Spanish)."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from tests.integration._seedlib import seed

from fichero_server.db import db_manager
from fichero_server.llm import LLMConfig
from fichero_server.llm.language_policy import parse_policy
from fichero_server.models import DocType, Document, FileType
from fichero_server.models.knowledge import EntityType, KnowledgeClaim, KnowledgeEntity
from fichero_server.workflows.tools import extract_entities_only as names
from fichero_server.workflows.tools import extract_svo_only as svo
from fichero_server.workflows.tools.extract_all import _EntitiesOnly, _EntityOnly
from fichero_server.workflows.tools.extractors import _write_kg_rows


@pytest.fixture(autouse=True)
def _no_seeding(monkeypatch):
    monkeypatch.setenv("FICHERO_SKIP_DEFAULT_WORKFLOWS", "1")
    monkeypatch.setattr(svo, "configured_policy", lambda: parse_policy(None))


def _library(tmp_path: Path, text: str):
    library_path = tmp_path / "wiring.fichero"
    seed(library_path)
    db = db_manager.get_database(library_path)
    db.save(Document(id="d1", name="acta.txt", doc_type=DocType.file, file_type=FileType.text, page_content=text))
    return library_path, db


def _state(library_path):
    return {"library_path": str(library_path), "selected_doc_ids": ["d1"], "task_id": "wiring"}


def test_the_names_step_drops_a_month_and_keeps_a_person_with_one(tmp_path, monkeypatch):
    library_path, db = _library(tmp_path, "Julio Cesar vecino de Valdoro firmó en Noviembre.")

    async def answer(**kwargs):
        return _EntitiesOnly(people=[_EntityOnly(name="Julio Cesar", aliases=[])],
                             places=[_EntityOnly(name="Noviembre", aliases=[])])

    monkeypatch.setattr(names, "chat_structured_with_fallback", answer)
    before = {e.canonical_name for e in db.query(KnowledgeEntity)}
    asyncio.run(names.extract_entities_only({"documents": [{"id": "d1"}]}, _state(library_path),
                                            LLMConfig(provider="openai", model="gpt-4o-mini")))
    assert {e.canonical_name for e in db.query(KnowledgeEntity)} - before == {"Julio Cesar"}


def test_the_statements_step_reads_the_page_across_its_line_breaks(tmp_path, monkeypatch):
    library_path, db = _library(tmp_path, "Lucas Pardo murió el 1.º de Ene-\nro de 1910 y su\nesposa firmó.")
    db.save(KnowledgeEntity(id="e1", canonical_name="Lucas Pardo", entity_type=EntityType.person,
                            source_document_ids=["d1"]))
    seen: list[str] = []

    async def page_claims(page_text, llm_config, instructions, extraction_sem):
        seen.append(page_text)
        return [{"subject": "Lucas Pardo", "verb": "murió", "object": "en 1910", "source_text": page_text}]

    written: list[dict] = []
    monkeypatch.setattr(svo, "claim_rejection", lambda *a, **k: None)
    monkeypatch.setattr(svo, "predicate_problem", lambda *a, **k: None)
    monkeypatch.setattr(svo, "_build_entity_items_for_section", lambda entity, key, claims: [{"i": 1}])
    monkeypatch.setattr(svo, "_write_kg_rows", lambda db, section, items, doc_id, **kw: written.append(kw))

    async def no_dates(**kwargs):
        schema = kwargs.get("schema")
        return schema(items=[])

    monkeypatch.setattr(svo, "_extract_page_claims", page_claims)
    monkeypatch.setattr(svo, "chat_structured_with_fallback", no_dates)
    asyncio.run(svo.extract_svo_only({"documents": [{"id": "d1"}], "entity_types": "people"}, _state(library_path),
                                     LLMConfig(provider="fake", model="fake-model")))
    assert seen and "\n" not in seen[0] and "1.º de Enero de 1910" in seen[0]
    assert written and written[0]["joined"].original.count("\n") == 2  # the lines stay, to anchor on


def test_a_dated_statement_goes_to_the_person_named_in_it(tmp_path, monkeypatch):
    library_path, db = _library(tmp_path, "El auto fue dictado por Lucas Pardo en 1918.")
    db.save(KnowledgeEntity(id="e1", canonical_name="Lucas Pardo", entity_type=EntityType.person,
                            source_document_ids=["d1"]))

    async def page_claims(page_text, llm_config, instructions, extraction_sem):
        return []

    async def dates(**kwargs):
        schema = kwargs["schema"]
        return schema(items=[{"date": "1918", "date_normalized": "1918", "verb": "fue dictado", "object": "el auto",
                              "source_text": "El auto fue dictado por Lucas Pardo en 1918"}])

    monkeypatch.setattr(svo, "_extract_page_claims", page_claims)
    monkeypatch.setattr(svo, "chat_structured_with_fallback", dates)
    asyncio.run(svo.extract_svo_only({"documents": [{"id": "d1"}]}, _state(library_path),
                                     LLMConfig(provider="fake", model="fake-model")))
    claims = db.query(KnowledgeClaim, source_document_id="d1")
    assert [c.subject_canonical for c in claims] == ["Lucas Pardo"]


_SPANISH = "Lucas Pardo vecino de Valdoro compareció ante el juzgado y dijo que firmaba el poder en la villa."


def _written(tmp_path, text):
    library_path, db = _library(tmp_path, text)
    section = {"name": "people", "schema_key": "people", "entity_type": EntityType.person}
    _write_kg_rows(db, section, [{"name": "Lucas Pardo", "verb": "", "object": ""}], "d1",
                   source_excerpt=text, provider="fake", model="fake", grounding_text=text)
    return [c.text for c in db.query(KnowledgeClaim, source_document_id="d1")]


def test_a_spanish_page_gets_no_english_is_a_person(tmp_path):
    assert not any(" is a " in t for t in _written(tmp_path, _SPANISH))


def test_an_english_page_still_gets_its_typed_default(tmp_path):
    text = "Lucas Pardo, a neighbour of Valdoro, appeared before the court and said that he signed the power of attorney."
    assert any("is a person" in t for t in _written(tmp_path, text))
