"""The parser's triples are a free tier for Find statements: proposals with their words, gated like a model's, and not
read off a reading too uncertain to read (#5637), tested to the spec: `source.job.find-statements.parser-tier`
(docs/contributor_manual/specs/source/models-chains-and-projects.md).

WHY: spaCy's subject-verb-object triples were used only to check a model's statements; a project with no model could
find no statements at all, though the parse is free and on this Mac.
"""

from __future__ import annotations

import pytest

import fichero_server.workflows.tools  # noqa: F401  (registers tools)
import fichero_server.workflows.tools.extract_svo_only as svo
from fichero_server.db import db_manager
from fichero_server.knowledge import spacy_svo
from fichero_server.llm import LLMConfig
from fichero_server.models import DocType, Document
from fichero_server.models.knowledge import EntityType, KnowledgeClaim, KnowledgeEntity
from fichero_server.recipes import runner
from fichero_server.workflows.runtime import build_initial_state
from tests.integration._seedlib import seed

TEXT = "Juan Asprilla vendió la mina de Istmina a Pedro Mosquera."
SPACY = LLMConfig(provider="spacy", model="es_core_news_sm")


def _page(tmp_path):
    library = tmp_path / "parser.fichero"
    seed(library)
    db = db_manager.get_database(library)
    db.save(Document(id="p1", name="1_Hoja.jpg", doc_type=DocType.page, page_content=TEXT, metadata={"page_number": 1}))
    db.save(KnowledgeEntity(id="e1", canonical_name="Juan Asprilla", entity_type=EntityType.person,
                            source_document_ids=["p1"]))
    return library, db


def _parse(monkeypatch, triples):
    monkeypatch.setattr(spacy_svo, "propose_triples", lambda text, language="es", **k: triples)
    monkeypatch.setattr(spacy_svo, "filter_proposals", lambda proposals, text: (list(proposals), []))


async def _no_model(*_a, **_k):
    raise AssertionError("the parser tier asked a language model")


async def _run(library):
    state = build_initial_state({"selected_doc_ids": ["p1"]}, library_path=str(library))
    return await svo.extract_svo_only({"documents": [{"id": "p1"}], "entity_types": "people"}, state, SPACY)


@pytest.mark.asyncio
async def test_the_parsers_triples_are_proposals_on_their_words_with_no_model(tmp_path, monkeypatch):
    library, db = _page(tmp_path)
    _parse(monkeypatch, [spacy_svo.ProposedTriple(subject="Juan Asprilla", verb="vendió", object="la mina de Istmina",
                                                  sentence=TEXT, char_start=0, char_end=len(TEXT))])
    monkeypatch.setattr(svo, "_extract_page_claims", _no_model)

    result = await _run(library)

    claims = [c for c in db.query(KnowledgeClaim) if c.source_document_id == "p1"]
    assert result["summary"]["claims_extracted"] == 1 and len(claims) == 1
    claim = claims[0]
    assert getattr(claim.curation_state, "value", claim.curation_state) == "unreviewed"  # a proposal, never a fact
    said = str(claim.model_dump())
    assert "vendió" in said and "la mina" in said
    assert "spacy" in said and "es_core_news_sm" in said  # marked as the parser's
    assert TEXT in said  # its words on the page (the line anchor is the shared writer's, `test_names_as_mentions`)


@pytest.mark.asyncio
async def test_a_triple_whose_subject_is_not_a_name_on_the_page_is_dropped(tmp_path, monkeypatch):
    library, db = _page(tmp_path)
    _parse(monkeypatch, [spacy_svo.ProposedTriple(subject="la escritura", verb="dice", object="algo",
                                                  sentence=TEXT, char_start=0, char_end=len(TEXT))])
    monkeypatch.setattr(svo, "_extract_page_claims", _no_model)
    await _run(library)
    assert not [c for c in db.query(KnowledgeClaim) if c.source_document_id == "p1"]


@pytest.mark.asyncio
async def test_a_page_read_too_uncertainly_gives_no_parser_statements_and_says_so(tmp_path, monkeypatch):
    library, db = _page(tmp_path)
    _parse(monkeypatch, [spacy_svo.ProposedTriple(subject="Juan Asprilla", verb="vendió", object="la mina",
                                                  sentence=TEXT, char_start=0, char_end=len(TEXT))])
    monkeypatch.setattr(svo, "_extract_page_claims", _no_model)
    monkeypatch.setattr(runner, "reading_too_uncertain", lambda db_, doc_id: doc_id == "p1")

    result = await _run(library)

    assert not [c for c in db.query(KnowledgeClaim) if c.source_document_id == "p1"]
    assert result["summary"]["left_out"] == [
        {"page_id": "p1", "page": "1_Hoja.jpg", "why": "its reading is too uncertain to find statements in"}]


def test_the_bundled_spacy_pipelines_are_offered_for_find_statements_never_ranked_over_a_model(client):
    """The person's to choose: offered for the step, with no rule rank, so a text model they have still comes first."""
    from fichero_server.recipes.start import _override

    answer = client.get("/api/recipes/candidates", params={"scripts": "Latn", "languages": "es",
                                                           "job": "find-statements"})
    assert answer.status_code == 200, answer.text
    parser = {i["id"]: i for i in answer.json()["items"] if i["id"].startswith("spacy:svo/")}
    assert "spacy:svo/es_core_news_sm@bundled" in parser
    assert all(i["rule_rank"] is None and not i["in_recipe_rules"] for i in parser.values())
    assert _override(parser["spacy:svo/es_core_news_sm@bundled"]["pin"]) == ("spacy", "es_core_news_sm")


def test_the_import_draft_finds_no_statements_on_an_uncertain_reading(db, monkeypatch):
    from fichero_server.importers import nlp_draft
    from fichero_server.knowledge import spacy_ner

    doc = Document(name="1.jpg", doc_type=DocType.page, page_content=TEXT, language="es")
    db.save(doc)
    parsed = []
    monkeypatch.setattr(spacy_ner, "is_pipeline_available", lambda _lang: True)
    monkeypatch.setattr(runner, "reading_too_uncertain", lambda db_, doc_id: True)
    nlp_draft.run_nlp_draft(db, doc, language="es", ner_fn=lambda text, language: [],
                            svo_fn=lambda text, language: parsed.append(text) or [],
                            filter_fn=lambda proposals, text: (proposals, []))
    assert parsed == []
