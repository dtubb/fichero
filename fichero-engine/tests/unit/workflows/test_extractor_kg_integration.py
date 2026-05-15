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



def _pydantic_from_json_response(json_str):
    """Translate a test's JSON-string fake_response into the Pydantic
    instance the new chat_structured_with_fallback path returns (#846).
    Section is detected from the JSON's top-level key."""
    import json as _json
    from fichero.workflows.tools.extractors import _SECTION_SCHEMAS
    parsed = _json.loads(json_str)
    if isinstance(parsed, dict):
        for key in _SECTION_SCHEMAS:
            if key in parsed:
                return _SECTION_SCHEMAS[key](items=parsed[key])
    raise ValueError(f"can't infer section from {parsed!r}")



class TestPeopleExtractorKG:
    @pytest.mark.asyncio
    async def test_creates_entity_and_claim_for_each_person(
        self, db, test_package, container_doc, llm_config
    ):
        from fichero.workflows.tools.extractors import _run_extractor, _SECTIONS

        people_section = next(s for s in _SECTIONS if s["name"] == "people_extract")
        fake_response = (
            '{"people": ['
            '{"name": "Juan Pérez", "context": "deed signer"},'
            '{"name": "María Angel", "context": "objected to the sale"}'
            "]}"
        )

        with patch(
            "fichero.workflows.tools.extractors.chat_structured_with_fallback",
            new=AsyncMock(return_value=_pydantic_from_json_response(fake_response)),
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
        fake_response = '{"people": [{"name": "Juan Pérez", "context": "x"}]}'

        with patch(
            "fichero.workflows.tools.extractors.chat_structured_with_fallback",
            new=AsyncMock(return_value=_pydantic_from_json_response(fake_response)),
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
        fake_response = '{"people": [{"name": "Juan Pérez", "context": "x"}]}'

        with patch(
            "fichero.workflows.tools.extractors.chat_structured_with_fallback",
            new=AsyncMock(return_value=_pydantic_from_json_response(fake_response)),
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
        fake_response = '{"people": [{"name": "Juan Pérez", "context": "x"}]}'
        cfg2 = LLMConfig(provider="anthropic", model="claude-sonnet-4-6")

        with patch(
            "fichero.workflows.tools.extractors.chat_structured_with_fallback",
            new=AsyncMock(return_value=_pydantic_from_json_response(fake_response)),
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
            '{"dates": ['
            '{"date": "12 de mayo de 1930", "date_normalized": "1930-05-12", '
            '"context": "deed signed"},'
            '{"date": "3 de agosto de 1931", "date_normalized": "1931-08-03", '
            '"context": "appeal filed"}'
            "]}"
        )

        with patch(
            "fichero.workflows.tools.extractors.chat_structured_with_fallback",
            new=AsyncMock(return_value=_pydantic_from_json_response(fake_response)),
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


class TestPerPageProvenance:
    @pytest.mark.asyncio
    async def test_per_page_extraction_writes_page_labels_and_excerpts(
        self, db, test_package, container_doc, llm_config
    ):
        """When the upstream node aggregated transcripts with the standard
        '\\n\\n---\\n\\n' separator, the extractor splits into per-page
        chunks, runs an LLM call per chunk, and saves claims with
        source_page_label + source_excerpt populated (#728 follow-up).
        """
        from fichero.workflows.tools.extractors import _run_extractor, _SECTIONS

        people_section = next(s for s in _SECTIONS if s["name"] == "people_extract")

        # Two-page aggregated text. Each page yields a different person so
        # we can verify per-page provenance, not just per-document.
        page1 = "On page one, María Angel signed the deed."
        page2 = "On page two, Juan Pérez objected to the sale."
        aggregated = f"{page1}\n\n---\n\n{page2}"

        # Mock returns a different Pydantic instance per page (#846).
        responses = iter([
            _pydantic_from_json_response(
                '{"people": [{"name": "María Angel", "context": "deed signer"}]}'
            ),
            _pydantic_from_json_response(
                '{"people": [{"name": "Juan Pérez", "context": "objected"}]}'
            ),
        ])

        async def fake_chat(*args, **kwargs):
            return next(responses)

        with patch(
            "fichero.workflows.tools.extractors.chat_structured_with_fallback",
            new=AsyncMock(side_effect=fake_chat),
        ):
            state = {
                "library_path": str(test_package),
                "selected_doc_ids": [container_doc.id],
            }
            await _run_extractor(people_section, {"text": aggregated}, state, llm_config)

        people = db.query(KnowledgeEntity, entity_type=EntityType.person)
        assert {p.canonical_name for p in people} == {"María Angel", "Juan Pérez"}

        claims = db.query(KnowledgeClaim, source_document_id=container_doc.id)
        assert len(claims) == 2
        page_labels = {c.source_page_label for c in claims}
        assert page_labels == {"Page 1", "Page 2"}

    @pytest.mark.asyncio
    async def test_single_chunk_no_separator_no_page_label(
        self, db, test_package, container_doc, llm_config
    ):
        """Workflows that don't aggregate (single-source text) get a
        single LLM call and no page_label — preserves pre-refactor
        behavior for non-aggregate paths."""
        from fichero.workflows.tools.extractors import _run_extractor, _SECTIONS

        people_section = next(s for s in _SECTIONS if s["name"] == "people_extract")
        # No '\n\n---\n\n' separator anywhere
        plain_text = "A single page of text mentioning María Angel only."
        fake_response = '{"people": [{"name": "María Angel", "context": "x"}]}'

        with patch(
            "fichero.workflows.tools.extractors.chat_structured_with_fallback",
            new=AsyncMock(return_value=_pydantic_from_json_response(fake_response)),
        ):
            state = {
                "library_path": str(test_package),
                "selected_doc_ids": [container_doc.id],
            }
            await _run_extractor(people_section, {"text": plain_text}, state, llm_config)

        claims = db.query(KnowledgeClaim, source_document_id=container_doc.id)
        assert len(claims) == 1
        # No page label when there was no separator (single chunk path)
        assert claims[0].source_page_label is None


class TestSingleFileSelectionWritesKG:
    """When the user selects a single file (md/txt/jpg etc) — not a folder
    or shared-parent group — KG entities/claims must still be persisted on
    the selected file (#1087, #1105). Pre-fix the extractor short-circuited
    because `_resolve_container_doc` returned None and the KG-write block
    was guarded by `if container and library_path:`."""

    @pytest.fixture
    def file_doc(self, db):
        from fichero.models import Document, DocType
        doc = Document(
            name="single.md",
            path="/test/single.md",
            doc_type=DocType.file,
        )
        db.save(doc)
        return doc

    @pytest.mark.asyncio
    async def test_extractor_writes_kg_on_selected_file(
        self, db, test_package, file_doc, llm_config
    ):
        from fichero.workflows.tools.extractors import _run_extractor, _SECTIONS

        people_section = next(s for s in _SECTIONS if s["name"] == "people_extract")
        fake_response = (
            '{"people": [{"name": "Juan Pérez", "context": "deed signer"}]}'
        )

        with patch(
            "fichero.workflows.tools.extractors.chat_structured_with_fallback",
            new=AsyncMock(return_value=_pydantic_from_json_response(fake_response)),
        ):
            state = {
                "library_path": str(test_package),
                "selected_doc_ids": [file_doc.id],
            }
            await _run_extractor(
                people_section, {"text": "..."}, state, llm_config,
            )

        # KnowledgeEntity rows persist regardless of where they're attached.
        people = db.query(KnowledgeEntity, entity_type=EntityType.person)
        assert len(people) == 1, "single-file selection must still write entities"
        # Provenance attaches to the selected file (the resolved write target).
        claims = db.query(KnowledgeClaim, source_document_id=file_doc.id)
        assert len(claims) == 1
        # And the dual-write artifact lives on the selected file too.
        artifacts = db.query(
            Artifact, document_id=file_doc.id, artifact_type="people"
        )
        assert len(artifacts) == 1
