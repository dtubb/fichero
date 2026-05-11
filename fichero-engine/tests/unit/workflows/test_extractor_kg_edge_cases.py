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



def _pydantic_from_json_response(json_str: str):
    """Translate a test's JSON-string fake_response into the Pydantic
    instance the new chat_structured_with_fallback path returns. The
    section is detected from which top-level key is present in the
    JSON. Used by _MIGRATION tests #846."""
    import json as _json
    from fichero.workflows.tools.extractors import _SECTION_SCHEMAS
    parsed = _json.loads(json_str)
    if isinstance(parsed, dict):
        for key in _SECTION_SCHEMAS:
            if key in parsed:
                schema = _SECTION_SCHEMAS[key]
                return schema(items=parsed[key])
    raise ValueError(f"can't infer section from {parsed!r}")


# ---------------------------------------------------------------------------
# All six generic extractors covered (parametrized)
# ---------------------------------------------------------------------------


async def _run_one_extractor(
    db, test_package, container_doc, llm_config, section_name, fake_response
):
    """Helper: run a single extractor with a mocked LLM response.

    Tests pass `fake_response` as a JSON string for ergonomics; we
    translate it into the Pydantic instance the new
    chat_structured_with_fallback path expects (#846 migration).
    """
    import json as _json
    from fichero.workflows.tools.extractors import (
        _run_extractor, _SECTIONS, _SECTION_SCHEMAS,
    )

    section = next(s for s in _SECTIONS if s["name"] == section_name)
    schema = _SECTION_SCHEMAS[section["schema_key"]]
    parsed = _json.loads(fake_response)
    items = parsed.get(section["schema_key"], [])
    fake_pydantic = schema(items=items)

    with patch(
        "fichero.workflows.tools.extractors.chat_structured_with_fallback",
        new=AsyncMock(return_value=fake_pydantic),
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
            "fichero.workflows.tools.extractors.chat_structured_with_fallback",
            new=AsyncMock(return_value=_pydantic_from_json_response(fake_response)),
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
        """Post #846: items missing a name field can't reach Python — the
        Pydantic schema (_SectionPerson.name: str) is required, and the
        grammar-constrained decoder can't emit a missing required field.
        This test now asserts the contract: only valid items survive,
        and the count matches what the LLM produced. The previous
        scenario (malformed JSON with missing fields silently skipped
        in Python) is now structurally impossible at the LLM layer."""
        from fichero.workflows.tools.extractors import _run_extractor, _SECTIONS

        people_section = next(s for s in _SECTIONS if s["name"] == "people_extract")
        # Only valid items can come back — schema rejects nameless ones at
        # the model's decode step.
        fake_response = (
            '{"people": [{"name": "Juan", "context": "valid"}]}'
        )

        with patch(
            "fichero.workflows.tools.extractors.chat_structured_with_fallback",
            new=AsyncMock(return_value=_pydantic_from_json_response(fake_response)),
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
            "fichero.workflows.tools.extractors.chat_structured_with_fallback",
            new=AsyncMock(return_value=_pydantic_from_json_response(fake_response)),
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
            "fichero.workflows.tools.extractors.chat_structured_with_fallback",
            new=AsyncMock(return_value=_pydantic_from_json_response(fake_response)),
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
            "fichero.workflows.tools.extractors.chat_structured_with_fallback",
            new=AsyncMock(return_value=_pydantic_from_json_response(fake_response)),
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
            "fichero.workflows.tools.extractors.chat_structured_with_fallback",
            new=AsyncMock(return_value=_pydantic_from_json_response(fake_response)),
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
            "fichero.workflows.tools.extractors.chat_structured_with_fallback",
            new=AsyncMock(return_value=_pydantic_from_json_response(fake_response)),
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
        """The SVO predicate lands on ``KnowledgeEntity.description``
        as a real sentence fragment — useful for the inspector view
        when there's no other description source yet. Replaces the
        old free-form `context` field (#892)."""
        from fichero.workflows.tools.extractors import _run_extractor, _SECTIONS

        people_section = next(s for s in _SECTIONS if s["name"] == "people_extract")
        fake_response = (
            '{"people": [{"name": "Juan", '
            '"verb": "signed", "object": "the deed in the 1930 sale"}]}'
        )

        with patch(
            "fichero.workflows.tools.extractors.chat_structured_with_fallback",
            new=AsyncMock(return_value=_pydantic_from_json_response(fake_response)),
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
        assert entity.description == "signed the deed in the 1930 sale"
