"""Tests for catalogue tool consuming pre-extracted claims (#727).

When the catalogue tool runs after per-section extractors (composable
workflow), the entity/claim rows already exist. The catalogue tool
should build the unified 9-section artifact from those rows instead
of running a fresh extraction LLM call.

When run after a bare Transcribe (monolithic workflow), no claims
exist; catalogue falls back to its original single-call extraction.
"""

from __future__ import annotations

from unittest.mock import patch, AsyncMock

import pytest

from fichero.knowledge_models import EntityType
from fichero.llm import LLMConfig
from fichero.models import Document, DocType


@pytest.fixture
def llm_config():
    return LLMConfig(provider="openai", model="gpt-4o-mini")


@pytest.fixture
def container_doc(db):
    doc = Document(name="Folder", path="/folder", doc_type=DocType.folder)
    db.save(doc)
    return doc


def _seed_claims(db, doc_id):
    """Pre-seed entity/claim rows as if extractors had already run."""
    from fichero.workflows.tools._entity_writer import upsert_entity, save_claim

    p1 = upsert_entity(db, "Juan Pérez", EntityType.person)
    p2 = upsert_entity(db, "María Angel", EntityType.person)
    place = upsert_entity(db, "Medellín", EntityType.location)
    org = upsert_entity(db, "Banco de la República", EntityType.organization)
    event = upsert_entity(db, "Audiencia de 1930", EntityType.event)
    keyword = upsert_entity(db, "minería", EntityType.concept)

    save_claim(db, "Juan Pérez signed the deed", doc_id, [p1])
    save_claim(db, "María Angel objected to the sale", doc_id, [p2])
    save_claim(db, "Medellín appellate court", doc_id, [place])
    save_claim(db, "Banco de la República involvement", doc_id, [org])
    save_claim(db, "1930 hearing on mining rights", doc_id, [event])
    save_claim(db, "central theme: minería", doc_id, [keyword])
    save_claim(
        db,
        "12 May 1930: deed signed",
        doc_id,
        [],
        metadata={"date_text": "12 de mayo de 1930", "date_normalized": "1930-05-12"},
    )


class TestCatalogueWithExistingClaims:
    @pytest.mark.asyncio
    async def test_skips_full_extraction_when_claims_exist(
        self, db, test_package, container_doc, llm_config
    ):
        """When claims/entities already exist for the document, the catalogue
        tool builds its data from those rows. The full-extraction LLM call
        is skipped — only a small resumen call runs."""
        from fichero.workflows.tools.catalogue import catalogue

        _seed_claims(db, container_doc.id)

        # The resumen call still happens. Mock it; capture how many times.
        with patch(
            "fichero.workflows.tools.catalogue.chat",
            new=AsyncMock(return_value="Resumen narrative."),
        ) as mock_chat:
            state = {
                "library_path": str(test_package),
                "selected_doc_ids": [container_doc.id],
            }
            result = await catalogue(
                {"text": "Source transcript text"},
                state,
                llm_config,
            )

        # At most ONE LLM call (for the resumen) — not the full extraction.
        assert mock_chat.call_count <= 1, (
            "catalogue should not run a full-extraction LLM call when claims "
            f"already exist; got {mock_chat.call_count} calls"
        )

        # The result still has the right shape.
        assert result.get("value") is not None
        data = result["value"]
        assert len(data.get("personas_clave", [])) == 2
        assert len(data.get("lugares", [])) == 1
        assert len(data.get("organizaciones", [])) == 1
        assert len(data.get("eventos_clave", [])) == 1
        assert len(data.get("palabras_clave", [])) == 1
        assert len(data.get("fechas", [])) == 1

    @pytest.mark.asyncio
    async def test_falls_back_to_full_extraction_when_no_claims(
        self, db, test_package, container_doc, llm_config
    ):
        """Monolithic workflow: catalogue runs after just Transcribe, no
        claims exist yet. Falls back to the original single-call full
        extraction."""
        from fichero.workflows.tools.catalogue import catalogue

        full_extraction_response = (
            '{"resumen": "narrative", "palabras_clave": [], "personas_clave": [], '
            '"fechas": [], "eventos_clave": [], "lugares": [], "organizaciones": []}'
        )

        with patch(
            "fichero.workflows.tools.catalogue.chat",
            new=AsyncMock(return_value=full_extraction_response),
        ) as mock_chat:
            state = {
                "library_path": str(test_package),
                "selected_doc_ids": [container_doc.id],
            }
            await catalogue(
                {"text": "Source transcript text"},
                state,
                llm_config,
            )

        # Original behavior: one LLM call to extract everything.
        assert mock_chat.call_count == 1
