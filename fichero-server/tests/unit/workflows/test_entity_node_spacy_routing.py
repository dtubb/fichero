"""A spaCy/local-NER model on an entity node runs NER, never the LLM factory.

Daniel's live failure: choosing "spaCy (local NLP)" for Extract Entities set a
run-level override of spacy/es_core_news_sm, which the entity node passed to the
LLM chat factory → "Unknown LLM provider: 'spacy'. Supported: openai, …". spaCy
NER is a separate on-device path; these tests pin that both entity nodes detect
a local-NER provider and route to it, and that the LLM factory is NOT reached.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.integration._seedlib import seed

from fichero_server.db import db_manager
from fichero_server.knowledge.ner import ExtractedEntity
from fichero_server.llm import LLMConfig
from fichero_server.models import Artifact, DocType, Document, FileType
from fichero_server.workflows.runtime import build_initial_state
import fichero_server.workflows.tools.entities as entities_tool
import fichero_server.workflows.tools.extract_entities_only as eeo


def _fake_provider(*spans):
    class _Prov:
        async def extract(self, text, *, language=None, **kwargs):
            return list(spans)

    return lambda provider, model: _Prov()


# --- generic Extract Entities node (entities.py) ---------------------------


@pytest.mark.asyncio
async def test_extract_entities_spacy_routes_to_ner_not_llm(monkeypatch):
    async def boom(*args, **kwargs):
        raise AssertionError("spaCy must not reach the LLM chat factory (process_text)")

    monkeypatch.setattr(entities_tool, "process_text", boom)
    monkeypatch.setattr(
        "fichero_server.workflows.ner.providers.get_ner_provider",
        _fake_provider(
            ExtractedEntity(name="Juan Pérez", type="person", provider_name="spacy"),
            ExtractedEntity(name="Popayán", type="location", provider_name="spacy"),
        ),
    )

    result = await entities_tool.extract_entities(
        {
            "text": "Juan Pérez en Popayán.",
            "entity_types": ["people", "organizations", "locations", "dates"],
        },
        {},
        LLMConfig(provider="spacy", model="es_core_news_sm"),
    )

    assert result["error"] is None
    assert "Juan Pérez" in result["entities"]["people"]
    assert "Popayán" in result["entities"]["locations"]


@pytest.mark.asyncio
async def test_extract_entities_llm_provider_still_uses_the_llm(monkeypatch):
    # Guard against over-correction: a normal cloud provider must still go
    # through the LLM path.
    called = {}

    async def fake_process_text(**kwargs):
        called["hit"] = True
        return {"value": {"people": ["X"]}, "text": "", "texts": [], "results": [], "artifacts": []}

    monkeypatch.setattr(entities_tool, "process_text", fake_process_text)

    await entities_tool.extract_entities(
        {"text": "something", "entity_types": ["people"]},
        {},
        LLMConfig(provider="openai", model="gpt-4o"),
    )
    assert called.get("hit") is True


# --- KG Extract Entities node (extract_entities_only.py) -------------------


def _seed_one_page(tmp_path: Path) -> tuple[Path, Document]:
    library_path = tmp_path / "spacy-route.fichero"
    seed(library_path)
    db = db_manager.get_database(library_path)

    source = tmp_path / "src.pdf"
    source.write_bytes(b"%PDF-1.4\n")
    parent = Document(
        id="route-root",
        name="root",
        path=str(source),
        doc_type=DocType.file,
        file_type=FileType.pdf,
        metadata={"canonical_external_id": "route-root"},
    )
    page = Document(
        id="route-page-1",
        parent_id=parent.id,
        name="page 1",
        doc_type=DocType.page,
        sequence=1,
        page_content="",
        metadata={
            "canonical_external_id": "route-root__page_001",
            "page_number": 1,
            "transcription": "",
        },
    )
    db.save(parent)
    db.save(page)
    db.save(
        Artifact(
            document_id=page.id,
            artifact_type="transcription",
            content="Juan de Guzmán firmó la escritura en Popayán.",
            data={"source": "test"},
            provider="test",
            model="fixture",
            step_name="import_artifacts",
            confidence=1.0,
        )
    )
    return library_path, page


@pytest.mark.asyncio
async def test_extract_entities_only_spacy_skips_the_llm(tmp_path, monkeypatch):
    library_path, page = _seed_one_page(tmp_path)

    async def boom(*args, **kwargs):
        raise AssertionError("spaCy must not reach chat_structured_with_fallback")

    monkeypatch.setattr(eeo, "chat_structured_with_fallback", boom)
    monkeypatch.setattr(
        "fichero_server.workflows.ner.providers.get_ner_provider",
        _fake_provider(
            ExtractedEntity(name="Juan de Guzmán", type="person", provider_name="spacy"),
            ExtractedEntity(name="Popayán", type="location", provider_name="spacy"),
        ),
    )

    state = build_initial_state(
        {"selected_doc_ids": [page.id]}, library_path=str(library_path)
    )
    result = await eeo.extract_entities_only(
        {"documents": [page]},
        state,
        LLMConfig(provider="spacy", model="es_core_news_sm"),
    )

    summary = result["summary"]
    # Two entities from the fake NER path, upserted without any LLM call.
    assert summary["entity_mentions_processed"] == 2
    assert summary["entities_created"] >= 1
