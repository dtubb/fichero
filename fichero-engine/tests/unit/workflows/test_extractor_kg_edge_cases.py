"""Edge case tests for catalogue extractor → KG integration (#728).

Companion to ``test_extractor_kg_integration.py``. The integration
tests cover the happy paths; this file exercises corners that broke or
could break: malformed items, missing fields, all-extractor coverage,
cross-document entity reuse, claim metadata fidelity for dates.
"""

from __future__ import annotations

from unittest.mock import patch, AsyncMock

import pytest

from fichero.knowledge_models import (
    EntityType,
    KnowledgeEntity,
    KnowledgeClaim,
)
from fichero.models import Document, DocType
from fichero.llm import LLMConfig


@pytest.fixture
def llm_config():
    return LLMConfig(provider="openai", model="gpt-4o-mini")


@pytest.fixture
def container_doc(db):
    doc = Document(name="Folder A", path="/folder_a", doc_type=DocType.folder)
    db.save(doc)
    return doc


@pytest.fixture
def second_doc(db):
    doc = Document(name="Folder B", path="/folder_b", doc_type=DocType.folder)
    db.save(doc)
    return doc


# ---------------------------------------------------------------------------
# All six generic extractors covered (parametrized)
# ---------------------------------------------------------------------------


async def _run_one_extractor(
    db, test_package, container_doc, llm_config, section_name, fake_response
):
    """Helper: run a single extractor with a mocked LLM response."""
    from fichero.workflows.tools.extractors import _run_extractor, _SECTIONS

    section = next(s for s in _SECTIONS if s["name"] == section_name)
    with patch(
        "fichero.workflows.tools.extractors.chat",
        new=AsyncMock(return_value=fake_response),
    ):
        state = {
            "library_path": str(test_package),
            "selected_doc_ids": [container_doc.id],
        }
        await _run_extractor(section, {"text": "..."}, state, llm_config)


def _assert_section_writes_kg(db, container_doc_id, entity_type):
    rows = db.query(KnowledgeEntity, entity_type=entity_type)
    assert len(rows) >= 1, f"no {entity_type} entity created"
    claims = db.query(KnowledgeClaim, source_document_id=container_doc_id)
    entity_ids = {row.id for row in rows}
    linked = [c for c in claims if any(eid in entity_ids for eid in c.entity_ids)]
    assert linked, f"no claim linking to {entity_type} entity"


class TestEachGenericExtractor:
    """One test per generic extractor — verifies KG writes happen for each
    of the six section types. Unrolled rather than parametrized because
    pytest-asyncio + parametrize has fixture wiring issues here."""

    @pytest.mark.asyncio
    async def test_people_writes_person_entities(
        self, db, test_package, container_doc, llm_config
    ):
        await _run_one_extractor(
            db, test_package, container_doc, llm_config,
            "people_extract",
            '{"people": [{"name": "X Y", "context": "c"}]}',
        )
        _assert_section_writes_kg(db, container_doc.id, EntityType.person)

    @pytest.mark.asyncio
    async def test_places_writes_location_entities(
        self, db, test_package, container_doc, llm_config
    ):
        await _run_one_extractor(
            db, test_package, container_doc, llm_config,
            "places_extract",
            '{"places": [{"name": "Lugar", "context": "c"}]}',
        )
        _assert_section_writes_kg(db, container_doc.id, EntityType.location)

    @pytest.mark.asyncio
    async def test_organizations_writes_organization_entities(
        self, db, test_package, container_doc, llm_config
    ):
        await _run_one_extractor(
            db, test_package, container_doc, llm_config,
            "organizations_extract",
            '{"organizations": [{"name": "Org", "context": "c"}]}',
        )
        _assert_section_writes_kg(db, container_doc.id, EntityType.organization)

    @pytest.mark.asyncio
    async def test_events_writes_event_entities(
        self, db, test_package, container_doc, llm_config
    ):
        await _run_one_extractor(
            db, test_package, container_doc, llm_config,
            "events_extract",
            '{"events": [{"event": "E", "context": "c"}]}',
        )
        _assert_section_writes_kg(db, container_doc.id, EntityType.event)

    @pytest.mark.asyncio
    async def test_keywords_writes_concept_entities(
        self, db, test_package, container_doc, llm_config
    ):
        await _run_one_extractor(
            db, test_package, container_doc, llm_config,
            "keywords_extract",
            '{"keywords": ["alpha", "beta"]}',
        )
        _assert_section_writes_kg(db, container_doc.id, EntityType.concept)


# ---------------------------------------------------------------------------
# Cross-document entity reuse — the whole point of the KG layer
# ---------------------------------------------------------------------------


class TestCrossDocumentEntityReuse:
    @pytest.mark.asyncio
    async def test_same_person_in_two_docs_dedupes_to_one_entity(
        self, db, test_package, container_doc, second_doc, llm_config
    ):
        """Running people extractor on two different documents that mention
        the same person should produce ONE entity row and TWO claims (one
        per document). This is what makes 'click María Angel → see all
        sources mentioning her' work in 0.0.3+."""
        from fichero.workflows.tools.extractors import _run_extractor, _SECTIONS

        people_section = next(s for s in _SECTIONS if s["name"] == "people_extract")
        fake_response = (
            '{"people": [{"name": "María Angel", '
            '"context": "appears in both"}]}'
        )

        with patch(
            "fichero.workflows.tools.extractors.chat",
            new=AsyncMock(return_value=fake_response),
        ):
            await _run_extractor(
                people_section,
                {"text": "..."},
                {
                    "library_path": str(test_package),
                    "selected_doc_ids": [container_doc.id],
                },
                llm_config,
            )
            await _run_extractor(
                people_section,
                {"text": "..."},
                {
                    "library_path": str(test_package),
                    "selected_doc_ids": [second_doc.id],
                },
                llm_config,
            )

        people = db.query(KnowledgeEntity, entity_type=EntityType.person)
        assert len(people) == 1, "same canonical_name across docs = one entity"

        claims = db.all(KnowledgeClaim)
        doc_ids = {c.source_document_id for c in claims}
        assert doc_ids == {container_doc.id, second_doc.id}
        assert len(claims) == 2
        assert all(people[0].id in c.entity_ids for c in claims)


# ---------------------------------------------------------------------------
# Malformed / missing fields
# ---------------------------------------------------------------------------


class TestMalformedItems:
    @pytest.mark.asyncio
    async def test_missing_canonical_name_skipped(
        self, db, test_package, container_doc, llm_config
    ):
        """An item with no 'nombre'/'name' field is silently skipped — we
        don't crash the extractor or write a nameless entity row."""
        from fichero.workflows.tools.extractors import _run_extractor, _SECTIONS

        people_section = next(s for s in _SECTIONS if s["name"] == "people_extract")
        # Two items: one valid, one missing nombre
        fake_response = (
            '{"people": ['
            '{"name": "Juan", "context": "valid"},'
            '{"context": "no name field"}'
            "]}"
        )

        with patch(
            "fichero.workflows.tools.extractors.chat",
            new=AsyncMock(return_value=fake_response),
        ):
            await _run_extractor(
                people_section,
                {"text": "..."},
                {
                    "library_path": str(test_package),
                    "selected_doc_ids": [container_doc.id],
                },
                llm_config,
            )

        people = db.query(KnowledgeEntity, entity_type=EntityType.person)
        assert len(people) == 1
        assert people[0].canonical_name == "Juan"

    @pytest.mark.asyncio
    async def test_keywords_as_bare_strings_handled(
        self, db, test_package, container_doc, llm_config
    ):
        """Keywords come through as flat strings, not objects. The extractor
        wraps each into a minimal {nombre: str} so the upsert still works."""
        from fichero.workflows.tools.extractors import _run_extractor, _SECTIONS

        keywords_section = next(s for s in _SECTIONS if s["name"] == "keywords_extract")
        fake_response = '{"keywords": ["mining", "1930s", "Antioquia"]}'

        with patch(
            "fichero.workflows.tools.extractors.chat",
            new=AsyncMock(return_value=fake_response),
        ):
            await _run_extractor(
                keywords_section,
                {"text": "..."},
                {
                    "library_path": str(test_package),
                    "selected_doc_ids": [container_doc.id],
                },
                llm_config,
            )

        concepts = db.query(KnowledgeEntity, entity_type=EntityType.concept)
        names = {c.canonical_name for c in concepts}
        assert names == {"mining", "1930s", "Antioquia"}

    @pytest.mark.asyncio
    async def test_empty_items_no_kg_writes(
        self, db, test_package, container_doc, llm_config
    ):
        """If the LLM returns an empty list, no KG rows are created."""
        from fichero.workflows.tools.extractors import _run_extractor, _SECTIONS

        people_section = next(s for s in _SECTIONS if s["name"] == "people_extract")
        fake_response = '{"people": []}'

        with patch(
            "fichero.workflows.tools.extractors.chat",
            new=AsyncMock(return_value=fake_response),
        ):
            await _run_extractor(
                people_section,
                {"text": "..."},
                {
                    "library_path": str(test_package),
                    "selected_doc_ids": [container_doc.id],
                },
                llm_config,
            )

        people = db.query(KnowledgeEntity, entity_type=EntityType.person)
        assert len(people) == 0
        claims = db.query(KnowledgeClaim, source_document_id=container_doc.id)
        assert len(claims) == 0


# ---------------------------------------------------------------------------
# Date claim metadata fidelity
# ---------------------------------------------------------------------------


class TestDateClaimMetadata:
    @pytest.mark.asyncio
    async def test_date_normalized_preserved_in_claim_metadata(
        self, db, test_package, container_doc, llm_config
    ):
        """Date claims must round-trip the normalized date in
        ``metadata['date_normalized']`` so future range queries work."""
        from fichero.workflows.tools.extractors import _run_extractor, _SECTIONS

        dates_section = next(s for s in _SECTIONS if s["name"] == "dates_extract")
        fake_response = (
            '{"dates": ['
            '{"date": "12 de mayo de 1930", "date_normalized": "1930-05-12", '
            '"context": "deed signed"}'
            "]}"
        )

        with patch(
            "fichero.workflows.tools.extractors.chat",
            new=AsyncMock(return_value=fake_response),
        ):
            await _run_extractor(
                dates_section,
                {"text": "..."},
                {
                    "library_path": str(test_package),
                    "selected_doc_ids": [container_doc.id],
                },
                llm_config,
            )

        claims = db.query(KnowledgeClaim, source_document_id=container_doc.id)
        assert len(claims) == 1
        assert claims[0].metadata.get("date_normalized") == "1930-05-12"
        assert claims[0].metadata.get("date_text") == "12 de mayo de 1930"

    @pytest.mark.asyncio
    async def test_date_range_normalized_preserved(
        self, db, test_package, container_doc, llm_config
    ):
        """Range dates ('1930-05-12/1930-08-04') survive the metadata
        round-trip intact."""
        from fichero.workflows.tools.extractors import _run_extractor, _SECTIONS

        dates_section = next(s for s in _SECTIONS if s["name"] == "dates_extract")
        fake_response = (
            '{"dates": ['
            '{"date": "from May to August 1930", '
            '"date_normalized": "1930-05-12/1930-08-04", '
            '"context": "litigation period"}'
            "]}"
        )

        with patch(
            "fichero.workflows.tools.extractors.chat",
            new=AsyncMock(return_value=fake_response),
        ):
            await _run_extractor(
                dates_section,
                {"text": "..."},
                {
                    "library_path": str(test_package),
                    "selected_doc_ids": [container_doc.id],
                },
                llm_config,
            )

        claim = db.query(KnowledgeClaim, source_document_id=container_doc.id)[0]
        assert "/" in claim.metadata.get("date_normalized", "")


# ---------------------------------------------------------------------------
# Aliases (the canonical-vs-alternative-spelling pattern)
# ---------------------------------------------------------------------------


class TestAliasPersistence:
    @pytest.mark.asyncio
    async def test_alternative_spellings_become_entity_aliases(
        self, db, test_package, container_doc, llm_config
    ):
        """When the LLM emits ``ortografias_alternativas`` for a person,
        those land on ``KnowledgeEntity.aliases`` so the future alias
        resolver (already at /api/entities/resolve/{value}) can find them."""
        from fichero.workflows.tools.extractors import _run_extractor, _SECTIONS

        people_section = next(s for s in _SECTIONS if s["name"] == "people_extract")
        fake_response = (
            '{"people": [{'
            '"name": "María Angel", '
            '"alternative_spellings": ["M. Angel", "Maria Angel"], '
            '"context": "appellant"}]}'
        )

        with patch(
            "fichero.workflows.tools.extractors.chat",
            new=AsyncMock(return_value=fake_response),
        ):
            await _run_extractor(
                people_section,
                {"text": "..."},
                {
                    "library_path": str(test_package),
                    "selected_doc_ids": [container_doc.id],
                },
                llm_config,
            )

        entity = db.query(KnowledgeEntity, entity_type=EntityType.person)[0]
        assert "M. Angel" in entity.aliases
        assert "Maria Angel" in entity.aliases


# ---------------------------------------------------------------------------
# Description (context) lands on the entity, not just the claim
# ---------------------------------------------------------------------------


class TestEntityDescription:
    @pytest.mark.asyncio
    async def test_first_run_context_becomes_entity_description(
        self, db, test_package, container_doc, llm_config
    ):
        """The 'context' field from the extractor lands on
        ``KnowledgeEntity.description`` — useful for the inspector view
        when there's no other description source yet."""
        from fichero.workflows.tools.extractors import _run_extractor, _SECTIONS

        people_section = next(s for s in _SECTIONS if s["name"] == "people_extract")
        fake_response = (
            '{"people": [{"name": "Juan", '
            '"context": "deed signer in 1930 sale"}]}'
        )

        with patch(
            "fichero.workflows.tools.extractors.chat",
            new=AsyncMock(return_value=fake_response),
        ):
            await _run_extractor(
                people_section,
                {"text": "..."},
                {
                    "library_path": str(test_package),
                    "selected_doc_ids": [container_doc.id],
                },
                llm_config,
            )

        entity = db.query(KnowledgeEntity, canonical_name="Juan")[0]
        assert entity.description == "deed signer in 1930 sale"
