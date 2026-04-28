"""Integration tests for catalogue extractors writing KG rows (#728).

After Phase 2 of the typed-entity-storage plan, extractors call the
``_entity_writer`` helpers to write KnowledgeEntity + KnowledgeClaim
rows alongside the existing Artifact write (dual-write pattern — keeps
markdown for debug/audit, adds KG for query/search).
"""

from __future__ import annotations

from unittest.mock import patch, AsyncMock

import pytest

from fichero.knowledge_models import (
    EntityType,
    KnowledgeEntity,
    KnowledgeClaim,
)
from fichero.models import Artifact, Document, DocType
from fichero.llm import LLMConfig


@pytest.fixture
def llm_config():
    return LLMConfig(provider="openai", model="gpt-4o-mini")


@pytest.fixture
def container_doc(db):
    """A folder document that catalogue extractors save artifacts onto."""
    doc = Document(
        name="Test Folder",
        path="/test/folder",
        doc_type=DocType.folder,
    )
    db.save(doc)
    return doc


class TestPeopleExtractorKG:
    @pytest.mark.asyncio
    async def test_creates_entity_and_claim_for_each_person(
        self, db, test_package, container_doc, llm_config
    ):
        from fichero.workflows.tools.extractors import _run_extractor, _SECTIONS

        people_section = next(s for s in _SECTIONS if s["name"] == "people_extract")
        fake_response = (
            '{"personas_clave": ['
            '{"nombre": "Juan Pérez", "contexto": "deed signer"},'
            '{"nombre": "María Angel", "contexto": "objected to the sale"}'
            "]}"
        )

        with patch(
            "fichero.workflows.tools.extractors.chat",
            new=AsyncMock(return_value=fake_response),
        ):
            state = {
                "library_path": str(test_package),
                "selected_doc_ids": [container_doc.id],
            }
            await _run_extractor(people_section, {"text": "..."}, state, llm_config)

        people = db.query(KnowledgeEntity, entity_type=EntityType.person)
        assert len(people) == 2
        names = {p.canonical_name for p in people}
        assert names == {"Juan Pérez", "María Angel"}

        claims = db.query(KnowledgeClaim, source_document_id=container_doc.id)
        assert len(claims) == 2
        # Each claim links to exactly one person
        for claim in claims:
            assert len(claim.entity_ids) == 1
            assert claim.entity_ids[0] in {p.id for p in people}

    @pytest.mark.asyncio
    async def test_dual_write_keeps_markdown_artifact(
        self, db, test_package, container_doc, llm_config
    ):
        """Per Daniel: keep markdown artifact alongside KG rows for debug."""
        from fichero.workflows.tools.extractors import _run_extractor, _SECTIONS

        people_section = next(s for s in _SECTIONS if s["name"] == "people_extract")
        fake_response = '{"personas_clave": [{"nombre": "Juan Pérez", "contexto": "x"}]}'

        with patch(
            "fichero.workflows.tools.extractors.chat",
            new=AsyncMock(return_value=fake_response),
        ):
            state = {
                "library_path": str(test_package),
                "selected_doc_ids": [container_doc.id],
            }
            await _run_extractor(people_section, {"text": "..."}, state, llm_config)

        artifacts = db.query(
            Artifact, document_id=container_doc.id, artifact_type="people"
        )
        assert len(artifacts) == 1
        assert artifacts[0].content  # markdown rendering

    @pytest.mark.asyncio
    async def test_same_model_rerun_hits_cache_no_duplicate(
        self, db, test_package, container_doc, llm_config
    ):
        """Same provider/model re-run hits the artifact cache; no duplicate
        KG rows from the cached path."""
        from fichero.workflows.tools.extractors import _run_extractor, _SECTIONS

        people_section = next(s for s in _SECTIONS if s["name"] == "people_extract")
        fake_response = '{"personas_clave": [{"nombre": "Juan Pérez", "contexto": "x"}]}'

        with patch(
            "fichero.workflows.tools.extractors.chat",
            new=AsyncMock(return_value=fake_response),
        ):
            state = {
                "library_path": str(test_package),
                "selected_doc_ids": [container_doc.id],
            }
            await _run_extractor(people_section, {"text": "..."}, state, llm_config)
            await _run_extractor(people_section, {"text": "..."}, state, llm_config)

        people = db.query(KnowledgeEntity, entity_type=EntityType.person)
        assert len(people) == 1

        claims = db.query(KnowledgeClaim, source_document_id=container_doc.id)
        assert len(claims) == 1, "second run cache-hit should not write again"

    @pytest.mark.asyncio
    async def test_different_model_rerun_dedups_entity_appends_claim(
        self, db, test_package, container_doc, llm_config
    ):
        """Different provider/model bypasses the artifact cache. Entity
        dedup still works (one entity row by canonical_name); claims
        accumulate as a provenance trail of two extraction runs."""
        from fichero.workflows.tools.extractors import _run_extractor, _SECTIONS

        people_section = next(s for s in _SECTIONS if s["name"] == "people_extract")
        fake_response = '{"personas_clave": [{"nombre": "Juan Pérez", "contexto": "x"}]}'
        cfg2 = LLMConfig(provider="anthropic", model="claude-sonnet-4-6")

        with patch(
            "fichero.workflows.tools.extractors.chat",
            new=AsyncMock(return_value=fake_response),
        ):
            state = {
                "library_path": str(test_package),
                "selected_doc_ids": [container_doc.id],
            }
            await _run_extractor(people_section, {"text": "..."}, state, llm_config)
            await _run_extractor(people_section, {"text": "..."}, state, cfg2)

        people = db.query(KnowledgeEntity, entity_type=EntityType.person)
        assert len(people) == 1, "entity dedup spans providers"

        claims = db.query(KnowledgeClaim, source_document_id=container_doc.id)
        assert len(claims) == 2
        assert all(people[0].id in c.entity_ids for c in claims)


class TestDatesExtractorKG:
    @pytest.mark.asyncio
    async def test_dates_create_claims_no_entities(
        self, db, test_package, container_doc, llm_config
    ):
        """Date sections produce claim-only rows; no canonical entity."""
        from fichero.workflows.tools.extractors import _run_extractor, _SECTIONS

        dates_section = next(s for s in _SECTIONS if s["name"] == "dates_extract")
        fake_response = (
            '{"fechas": ['
            '{"fecha": "12 de mayo de 1930", "fecha_normalizada": "1930-05-12", '
            '"contexto": "deed signed"},'
            '{"fecha": "3 de agosto de 1931", "fecha_normalizada": "1931-08-03", '
            '"contexto": "appeal filed"}'
            "]}"
        )

        with patch(
            "fichero.workflows.tools.extractors.chat",
            new=AsyncMock(return_value=fake_response),
        ):
            state = {
                "library_path": str(test_package),
                "selected_doc_ids": [container_doc.id],
            }
            await _run_extractor(dates_section, {"text": "..."}, state, llm_config)

        # No entities created for dates
        entities = db.all(KnowledgeEntity)
        assert len(entities) == 0

        # Two claims, with normalized date in metadata
        claims = db.query(KnowledgeClaim, source_document_id=container_doc.id)
        assert len(claims) == 2
        normalized_dates = {
            c.metadata.get("date_normalized") for c in claims
        }
        assert normalized_dates == {"1930-05-12", "1931-08-03"}
        assert all(c.entity_ids == [] for c in claims)
