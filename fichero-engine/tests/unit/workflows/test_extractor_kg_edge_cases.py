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

    async def test_keyword_claims_have_entity_ids_populated(
        self, db, test_package, container_doc, llm_config
    ):
        """Keyword claims must have their entity_ids populated with the
        keyword entity's ID. This enables the graph traversal path from
        keyword entity → claims to work (see #1296).

        Test includes short keywords (<4 chars) which previously had empty
        entity_ids due to alias scan threshold — those must be fixed too."""
        await _run_one_extractor(
            db, test_package, container_doc, llm_config,
            "keywords_extract",
            '{"keywords": ["mining", "Antioquia", "AI", "art", "RNA"]}',
        )
        # Find all keyword claims
        claims = db.all(KnowledgeClaim)
        keyword_claims = [c for c in claims if c.source_document_id == container_doc.id]

        # Each claim should have entity_ids populated, including short keywords
        assert len(keyword_claims) == 5, f"should have 5 keyword claims, got {len(keyword_claims)}"
        for claim in keyword_claims:
            assert claim.entity_ids, f"keyword claim '{claim.text}' has empty entity_ids (BUG #1296)"
            assert len(claim.entity_ids) > 0, f"keyword claim '{claim.text}' entity_ids is empty list"


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
# #1003 — silent zero-entity pages must surface in the activity log
# ---------------------------------------------------------------------------


class TestSilentZeroEntityLogging:
    """#1003: a page producing zero entities used to be skipped without a
    trace, indistinguishable from a silent extraction failure. Every page
    must now emit a structured log line — populated or empty."""

    @pytest.mark.asyncio
    async def test_populated_page_logs_structured_counts(
        self, db, test_package, container_doc, llm_config, caplog
    ):
        from fichero.workflows.tools.extractors import _run_extractor, _SECTIONS

        people_section = next(s for s in _SECTIONS if s["name"] == "people_extract")
        fake_response = '{"people": [{"name": "Juan", "context": "valid"}]}'

        with patch(
            "fichero.workflows.tools.extractors.chat_structured_with_fallback",
            new=AsyncMock(return_value=_pydantic_from_json_response(fake_response)),
        ), caplog.at_level("INFO", logger="fichero.workflows.tools.extractors"):
            await _run_extractor(
                people_section,
                {"text": "..."},
                {
                    "library_path": str(test_package),
                    "selected_doc_ids": [container_doc.id],
                },
                llm_config,
            )

        assert any(
            "items_in=1" in r.message
            and "entities_written=1" in r.message
            and "claims_written=1" in r.message
            for r in caplog.records
        ), f"expected structured _write_kg_rows summary, got: {[r.message for r in caplog.records]}"

    @pytest.mark.asyncio
    async def test_empty_page_in_multipage_doc_logs_zero_items_explicitly(
        self, db, test_package, container_doc, llm_config, caplog
    ):
        """The #1003 bug scenario: a multi-page doc where SOME pages return
        zero entities. The populated pages keep ``any(chunk_results)`` true
        so the KG-write loop still runs — and the empty page must emit an
        explicit 'produced 0 items' line instead of being skipped silently.
        """
        from fichero.workflows.tools.extractors import _run_extractor, _SECTIONS

        people_section = next(s for s in _SECTIONS if s["name"] == "people_extract")

        # Page 1 yields a person; page 2 yields nothing.
        aggregated = (
            "On page one, María Angel signed the deed.\n\n---\n\n"
            "Page two is boilerplate with no named people."
        )
        responses = iter([
            _pydantic_from_json_response(
                '{"people": [{"name": "María Angel", "context": "deed signer"}]}'
            ),
            _pydantic_from_json_response('{"people": []}'),
        ])

        async def fake_chat(*args, **kwargs):
            return next(responses)

        with patch(
            "fichero.workflows.tools.extractors.chat_structured_with_fallback",
            new=AsyncMock(side_effect=fake_chat),
        ), caplog.at_level("INFO", logger="fichero.workflows.tools.extractors"):
            await _run_extractor(
                people_section,
                {"text": aggregated},
                {
                    "library_path": str(test_package),
                    "selected_doc_ids": [container_doc.id],
                },
                llm_config,
            )

        assert any(
            "Page 2 produced 0 items" in r.message for r in caplog.records
        ), f"expected explicit zero-items log for Page 2, got: {[r.message for r in caplog.records]}"
        # Page 1 still gets its structured summary.
        assert any(
            "Page 1" in r.message and "items_in=1" in r.message
            for r in caplog.records
        ), f"expected structured summary for Page 1, got: {[r.message for r in caplog.records]}"


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

    @pytest.mark.asyncio
    async def test_degenerate_predicate_yields_none_description(
        self, db, test_package, container_doc, llm_config
    ):
        """Single-word predicates like 'called' or 'noted' must NOT
        end up as the entity description. Empty is a better signal
        than misleading content. (#1016)"""
        from fichero.workflows.tools.extractors import _run_extractor, _SECTIONS

        people_section = next(s for s in _SECTIONS if s["name"] == "people_extract")
        fake_response = (
            '{"people": ['
            '{"name": "Elisabet", "verb": "called", "object": ""},'
            '{"name": "Davidson", "verb": "noted", "object": ""},'
            '{"name": "Marta", "verb": "is", "object": "the"}'
            ']}'
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

        for name in ("Elisabet", "Davidson", "Marta"):
            rows = db.query(KnowledgeEntity, canonical_name=name)
            assert rows, f"{name} should still be created as an entity"
            assert rows[0].description is None, (
                f"{name}: degenerate predicate should yield None, got "
                f"{rows[0].description!r}"
            )


# ---------------------------------------------------------------------------
# Description sanitiser — unit-level (no DB)
# ---------------------------------------------------------------------------


class TestSanitizeEntityDescription:
    """Direct unit tests for ``_sanitize_entity_description`` so the
    rejection rules are pinned independently of the extractor pipeline.
    (#1016)
    """

    def test_none_and_empty(self):
        from fichero.workflows.tools.extractors import _sanitize_entity_description
        assert _sanitize_entity_description(None, "Foo") is None
        assert _sanitize_entity_description("", "Foo") is None
        assert _sanitize_entity_description("   ", "Foo") is None

    def test_single_word_rejected(self):
        from fichero.workflows.tools.extractors import _sanitize_entity_description
        assert _sanitize_entity_description("called", "Elisabet") is None
        assert _sanitize_entity_description("noted", "Davidson") is None

    def test_two_words_rejected(self):
        from fichero.workflows.tools.extractors import _sanitize_entity_description
        assert _sanitize_entity_description("was published", "Foo") is None

    def test_all_function_words_rejected(self):
        from fichero.workflows.tools.extractors import _sanitize_entity_description
        assert _sanitize_entity_description("is the of", "Foo") is None
        assert _sanitize_entity_description("called as the", "Foo") is None

    def test_substring_of_canonical_rejected(self):
        from fichero.workflows.tools.extractors import _sanitize_entity_description
        assert _sanitize_entity_description(
            "Don Alfonso Garcia", "Don Alfonso Garcia Lopez"
        ) is None

    def test_real_description_kept(self):
        from fichero.workflows.tools.extractors import _sanitize_entity_description
        assert _sanitize_entity_description(
            "a neighbor and twenty-first-century artisanal miner", "Don Alfonso"
        ) == "a neighbor and twenty-first-century artisanal miner"
        assert _sanitize_entity_description(
            "served as the alcalde of Popayán", "Eugenio Córdoba"
        ) == "served as the alcalde of Popayán"


class TestInvariantViolationLogging:
    """Verify that extractor → KG round-trip violations surface in logs (#1017 layer 2).

    When extracted items violate invariants (no canonical name, degenerate
    descriptions, empty SVO), the activity log must show WHY a page is thin,
    not leave gaps unexplained. Tests that invariant violations are actually
    logged at WARNING level so operators see them during triage.
    """

    def test_anchorless_items_logged_as_violations(self, db, container_doc, caplog):
        """Items with no canonical name (the #1006/#1003 signature)
        should be flagged as violations in the WARNING log."""
        from fichero.workflows.tools.extractors import _SECTIONS, _write_kg_rows

        places_section = next(s for s in _SECTIONS if s["name"] == "places_extract")
        # Item with no name key — will be dropped by _write_kg_rows.
        items = [
            {"verb": "is", "object": "a significant location"},  # no name
        ]

        with caplog.at_level("WARNING", logger="fichero.workflows.tools.extractors"):
            _write_kg_rows(
                db, places_section, items, container_doc.id,
                page_label="Page 1",
                source_excerpt="some text",
                provider="openai",
                model="gpt-4o-mini",
            )

        # Should log an invariant violation for the missing canonical name.
        violations = [
            r.message for r in caplog.records
            if "invariant violations" in r.message
        ]
        assert violations, "expected WARNING with invariant violations for anchorless item"
        assert any("no canonical name" in v for v in violations)

    def test_degenerate_descriptions_logged_as_violations(self, db, container_doc, caplog):
        """Entity descriptions that are too short or echo the canonical name
        should be logged as violations, not silently dropped."""
        from fichero.workflows.tools.extractors import _SECTIONS, _write_kg_rows

        people_section = next(s for s in _SECTIONS if s["name"] == "people_extract")
        # Items with degenerate descriptions.
        items = [
            {"name": "Eugenio Córdoba", "context": "Eugenio Córdoba"},  # echoes name
            {"name": "Juan", "context": "the"},  # too short
        ]

        with caplog.at_level("WARNING", logger="fichero.workflows.tools.extractors"):
            _write_kg_rows(
                db, people_section, items, container_doc.id,
                page_label="Page 1",
                source_excerpt="some text",
                provider="openai",
                model="gpt-4o-mini",
            )

        violations = [
            r.message for r in caplog.records
            if "invariant violations" in r.message
        ]
        assert violations, "expected WARNING for degenerate descriptions"

    def test_page_summary_logs_items_in_and_written(self, db, container_doc, caplog):
        """Every page write should log items_in vs entities_written/claims_written
        so activity log shows when a page's items were lost or degraded (#1017)."""
        from fichero.workflows.tools.extractors import _SECTIONS, _write_kg_rows

        places_section = next(s for s in _SECTIONS if s["name"] == "places_extract")
        # Mixed items: some good, some anchorless.
        items = [
            {"name": "Popayán", "verb": "is", "object": "a city"},  # good
            {"verb": "has", "object": "significance"},  # anchorless — will drop
        ]

        with caplog.at_level("INFO", logger="fichero.workflows.tools.extractors"):
            _write_kg_rows(
                db, places_section, items, container_doc.id,
                page_label="Page 1",
                source_excerpt="some text",
                provider="openai",
                model="gpt-4o-mini",
            )

        # Should log structured summary with item counts.
        summaries = [
            r.message for r in caplog.records
            if "items_in=" in r.message and "entities_written=" in r.message
        ]
        assert summaries, "expected INFO log with item counts"
        # Should show items_in=2, entities_written=1 (one dropped).
        assert any("items_in=2" in s and "entities_written=1" in s for s in summaries)

    def test_svo_completeness_maintained_for_all_written_claims(self, db, container_doc):
        """Verify that after _write_kg_rows, every claim has non-None
        subject_canonical, predicate_verb, object_phrase (or all are None
        for synthetic/fallback SVO cases). This is the #1113 invariant."""
        from fichero.workflows.tools.extractors import _SECTIONS, _write_kg_rows
        from fichero.knowledge_models import KnowledgeClaim

        places_section = next(s for s in _SECTIONS if s["name"] == "places_extract")
        # Mix of LLM-SVO and legacy-context items.
        items = [
            {"name": "Chocó", "verb": "is", "object": "a Pacific region"},
            {"name": "Atrato", "context": "Atrato: a river"},
        ]

        _write_kg_rows(
            db, places_section, items, container_doc.id,
            page_label="Page 1",
            source_excerpt="some text",
            provider="openai",
            model="gpt-4o-mini",
        )

        claims = db.query(KnowledgeClaim, source_document_id=container_doc.id)
        assert len(claims) == 2, "both items should write claims"

        # SVO invariant: all three fields must be non-None.
        for claim in claims:
            assert claim.subject_canonical, (
                f"claim {claim.id!r} has no subject_canonical: {claim.text!r}"
            )
            assert claim.predicate_verb, (
                f"claim {claim.id!r} has no predicate_verb: {claim.text!r}"
            )
            assert claim.object_phrase, (
                f"claim {claim.id!r} has no object_phrase: {claim.text!r}"
            )

    def test_entity_description_invariant_enforced(self, db, container_doc):
        """Entity descriptions written to the KG must be None OR
        >=3 words AND not a substring of canonical_name. This prevents
        the silent #1016 / #1009 degradation."""
        from fichero.workflows.tools.extractors import _SECTIONS, _write_kg_rows
        from fichero.knowledge_models import KnowledgeEntity

        people_section = next(s for s in _SECTIONS if s["name"] == "people_extract")
        # Items: one with valid description, one with short description.
        items = [
            {
                "name": "Eugenio Córdoba",
                "context": "served as the alcalde of Popayán",
            },
            {
                "name": "María",
                "context": "a",  # too short
            },
        ]

        _write_kg_rows(
            db, people_section, items, container_doc.id,
            page_label="Page 1",
            source_excerpt="some text",
            provider="openai",
            model="gpt-4o-mini",
        )

        entities = db.query(KnowledgeEntity)
        assert len(entities) == 2, "both items should create entities"

        # Check invariants.
        for entity in entities:
            if entity.description is not None:
                # Must be >=3 words.
                words = entity.description.split()
                assert len(words) >= 3, (
                    f"{entity.canonical_name!r} description too short: "
                    f"{entity.description!r}"
                )
                # Must not be a substring of canonical name.
                assert (
                    entity.description.casefold()
                    not in entity.canonical_name.casefold()
                ), (
                    f"{entity.canonical_name!r} description echoes name: "
                    f"{entity.description!r}"
                )


def test_pronoun_subject_reuses_preceding_entity(db, container_doc):
    from fichero.knowledge_models import KnowledgeClaim
    from fichero.workflows.tools.extractors import _SECTIONS, _write_kg_rows

    section = next(s for s in _SECTIONS if s["name"] == "places_extract")
    _write_kg_rows(
        db,
        section,
        [
            {"name": "Rosario", "verb": "is", "object": "a street"},
            {"name": "they", "verb": "contains", "object": "a straw house"},
        ],
        container_doc.id,
    )

    claims = db.query(KnowledgeClaim, source_document_id=container_doc.id)
    assert {claim.subject_canonical for claim in claims} == {"Rosario"}
