"""Integration tests for catalogue extractors writing KG rows (#728).

After Phase 2 of the typed-entity-storage plan, extractors call the
``_entity_writer`` helpers to write KnowledgeEntity + KnowledgeClaim
rows alongside the existing Artifact write (dual-write pattern — keeps
markdown for debug/audit, adds KG for query/search).
"""

from __future__ import annotations

from unittest.mock import patch, AsyncMock

import pytest

from fichero.models.knowledge import (
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
    async def test_overlap_context_captures_entities_spanning_pages(
        self, db, test_package, container_doc, llm_config
    ):
        """When an entity name spans a page boundary (e.g., "Juan" ends
        page 1, "Pérez" starts page 2), overlap context (#971) prepends
        the tail of page 1 to page 2 so the LLM sees the full name.
        Without overlap, the entity would be truncated and missed."""
        from fichero.workflows.tools.extractors import _run_extractor, _SECTIONS

        people_section = next(s for s in _SECTIONS if s["name"] == "people_extract")

        # Entity spans page boundary: last word of page 1 is first word of page 2
        page1 = "On the first page, the attorney Juan"
        page2 = "Pérez reviewed the document carefully."
        aggregated = f"{page1}\n\n---\n\n{page2}"

        # Mock the LLM to extract the full name only when it sees both
        # parts (via overlap). Without overlap, would extract truncated.
        def fake_chat_with_overlap(prompt, **kwargs):
            # If prompt contains "Juan Pérez", we saw the overlap
            if "Juan" in prompt and "Pérez" in prompt:
                response_json = '{"people": [{"name": "Juan Pérez", "context": "attorney"}]}'
            else:
                # Truncated name when no overlap
                response_json = '{"people": []}'  # missed the entity
            return _pydantic_from_json_response(response_json)

        with patch(
            "fichero.workflows.tools.extractors.chat_structured_with_fallback",
            new=AsyncMock(side_effect=fake_chat_with_overlap),
        ):
            state = {
                "library_path": str(test_package),
                "selected_doc_ids": [container_doc.id],
            }
            await _run_extractor(
                people_section, {"text": aggregated}, state, llm_config
            )

        # With overlap context, "Juan Pérez" should be extracted
        people = db.query(KnowledgeEntity, entity_type=EntityType.person)
        assert len(people) == 1
        assert people[0].canonical_name == "Juan Pérez"

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


class TestClaimAttribution1113:
    """#1113: every claim must carry full SVO + provider/model attribution
    so #1111 (paragraph composition with citation arrows) has the data
    it needs and users can audit per-model claim quality.
    """

    @pytest.mark.asyncio
    async def test_llm_svo_passes_through_with_provider_model(
        self, db, test_package, container_doc, llm_config
    ):
        from fichero.workflows.tools.extractors import _run_extractor, _SECTIONS

        people_section = next(s for s in _SECTIONS if s["name"] == "people_extract")
        # The new extractor schema has verb/object — explicit LLM SVO.
        fake_response = (
            '{"people": [{"name": "Eugenio Córdoba", '
            '"verb": "served as", "object": "the alcalde of Popayán"}]}'
        )
        with patch(
            "fichero.workflows.tools.extractors.chat_structured_with_fallback",
            new=AsyncMock(return_value=_pydantic_from_json_response(fake_response)),
        ):
            state = {
                "library_path": str(test_package),
                "selected_doc_ids": [container_doc.id],
            }
            await _run_extractor(
                people_section, {"text": "..."}, state, llm_config,
            )
        claims = db.query(KnowledgeClaim, source_document_id=container_doc.id)
        assert len(claims) == 1
        c = claims[0]
        # Full SVO promoted to top-level fields (#984/#1113).
        assert c.subject_canonical == "Eugenio Córdoba"
        assert c.predicate_verb == "served as"
        assert c.object_phrase == "the alcalde of Popayán"
        # Composed sentence (no citation interpolation here).
        assert c.text == "Eugenio Córdoba served as the alcalde of Popayán."
        # Provider attribution from the LLMConfig.
        assert c.provider == "openai"
        # No "+heuristic-svo" suffix when the LLM gave us the SVO.
        assert c.model == "gpt-4o-mini"
        # Higher confidence for explicit-LLM SVO.
        assert c.confidence == 0.7

    def test_write_kg_rows_synthesises_svo_for_legacy_context_items(
        self, db, container_doc
    ):
        """When a cached legacy item arrives with only `context` (no
        verb/object), _write_kg_rows must synthesise SVO via the
        fallback so claim.predicate_verb / object_phrase land non-NULL.
        This is the critical #1113 invariant — claims with NULL SVO
        can't be rendered by the #1111 paragraph composer."""
        from fichero.workflows.tools.extractors import _SECTIONS, _write_kg_rows

        places_section = next(s for s in _SECTIONS if s["name"] == "places_extract")
        legacy_items = [
            {
                "name": "Chocó",
                "context": "Chocó: the region where artisanal mining occurs",
            }
        ]
        _write_kg_rows(
            db, places_section, legacy_items, container_doc.id,
            page_label="Page 1",
            source_excerpt="some page text",
            provider="openai",
            model="gpt-4o-mini",
        )
        claims = db.query(KnowledgeClaim, source_document_id=container_doc.id)
        assert len(claims) == 1
        c = claims[0]
        assert c.subject_canonical == "Chocó"
        assert c.predicate_verb == "is"
        assert c.object_phrase == "the region where artisanal mining occurs"
        # Honest hybrid label for synthesised SVO.
        assert c.provider == "openai"
        assert c.model == "gpt-4o-mini+heuristic-svo"
        # Lower confidence for synthesised SVO.
        assert c.confidence == 0.5

    def test_full_svo_invariant_holds_for_every_written_claim(
        self, db, container_doc
    ):
        """The #1113 acceptance gate: every claim written has non-None
        subject_canonical, predicate_verb, object_phrase. Mix of LLM-SVO
        items and legacy-context items in the same write call (the
        realistic extract_all output where some items have full SVO and
        some don't)."""
        from fichero.workflows.tools.extractors import _SECTIONS, _write_kg_rows

        places_section = next(s for s in _SECTIONS if s["name"] == "places_extract")
        items = [
            {"name": "Chocó", "verb": "is", "object": "a Pacific region"},
            {"name": "Atrato", "context": "drains westward"},
            {"name": "San Juan", "context": "San Juan: a tributary"},
        ]
        _write_kg_rows(
            db, places_section, items, container_doc.id,
            page_label="Page 1",
            source_excerpt="some page text",
            provider="openai",
            model="gpt-4o-mini",
        )
        claims = db.query(KnowledgeClaim, source_document_id=container_doc.id)
        assert len(claims) == 3
        for c in claims:
            assert c.subject_canonical, f"missing subject on {c.text!r}"
            assert c.predicate_verb, f"missing verb on {c.text!r}"
            assert c.object_phrase, f"missing object on {c.text!r}"
            assert c.provider == "openai"
            assert c.model and c.model.startswith("gpt-4o-mini")


class TestRerunIdempotence1120:
    """Regression for #1120: re-running extraction on a doc with existing
    KnowledgeEntity rows must not crash the backend with a duplicate-key
    PRIMARY KEY constraint error.

    The crash signature was an unrecoverable
    ``duckdb.FatalException: INTERNAL Error: Failed to append to
    PRIMARY_knowledgeentitys_0`` thrown out of ``Database.save`` when
    re-saving an existing entity row. The typed save layer is now
    defended via DELETE+INSERT fallback so the process survives even if
    the underlying ``INSERT OR REPLACE`` ever fails to resolve a PK
    conflict.
    """

    def test_write_kg_rows_is_idempotent_across_reruns(self, db, container_doc):
        """Two consecutive _write_kg_rows calls on the same doc with the
        same items must (a) not crash, (b) leave entity count unchanged,
        (c) not duplicate page-scoped claims (the in-writer dedup at
        save_claim catches identical (doc, page, entities, text>=90%)
        repeats)."""
        from fichero.workflows.tools.extractors import _SECTIONS, _write_kg_rows

        places_section = next(s for s in _SECTIONS if s["name"] == "places_extract")
        items = [
            {"name": "Chocó", "verb": "is", "object": "a Pacific region"},
            {"name": "Atrato", "verb": "drains", "object": "westward"},
        ]

        _write_kg_rows(
            db, places_section, items, container_doc.id,
            page_label="Page 1",
            source_excerpt="some page text",
            provider="openai",
            model="gpt-4o-mini",
        )
        entities_after_first = db.query(KnowledgeEntity, entity_type=EntityType.location)
        claims_after_first = db.query(
            KnowledgeClaim, source_document_id=container_doc.id
        )
        assert len(entities_after_first) == 2
        assert len(claims_after_first) == 2

        # Same items again — must not crash, must not create duplicate
        # entity rows, must not duplicate page-scoped claims.
        _write_kg_rows(
            db, places_section, items, container_doc.id,
            page_label="Page 1",
            source_excerpt="some page text",
            provider="openai",
            model="gpt-4o-mini",
        )
        entities_after_second = db.query(KnowledgeEntity, entity_type=EntityType.location)
        claims_after_second = db.query(
            KnowledgeClaim, source_document_id=container_doc.id
        )
        assert len(entities_after_second) == len(entities_after_first), (
            "rerun must not duplicate KnowledgeEntity rows"
        )
        assert len(claims_after_second) == len(claims_after_first), (
            "rerun on same (doc, page, entities, text) must hit the "
            "save_claim defense-in-depth dedup"
        )

    def test_db_save_recovers_from_duplicate_pk_on_entity(self, db):
        """Direct test of the typed-save defense (#1120 layer 1): even
        if a caller mistakenly tries to INSERT a fresh entity instance
        carrying the same id as an existing row, ``db.save`` must NOT
        raise a FatalException — it must transparently overwrite via
        the DELETE+INSERT fallback. This locks the contract that
        ``save`` is idempotent on id."""
        first = KnowledgeEntity(
            canonical_name="Atrato",
            entity_type=EntityType.location,
            description="first description",
        )
        db.save(first)

        # New instance, SAME id, different description — simulates the
        # pathological "save again with same id" path that surfaced in
        # the live crash. Must succeed (overwrite), not raise.
        same_id_again = KnowledgeEntity(
            id=first.id,
            canonical_name="Atrato",
            entity_type=EntityType.location,
            description="second description",
        )
        db.save(same_id_again)

        rows = db.query(KnowledgeEntity, entity_type=EntityType.location)
        assert len(rows) == 1
        assert rows[0].id == first.id
        assert rows[0].description == "second description"

    def test_db_save_uses_native_on_conflict_upsert(self, db):
        """The #1120 root-cause fix: ``Database.save`` must use DuckDB's
        native ``INSERT ... ON CONFLICT (id) DO UPDATE SET ...`` UPSERT
        rather than ``INSERT OR REPLACE``. Round-trip save → modify →
        save → assert the row is updated, not duplicated, and no crash
        occurs. This locks the contract that ``save`` is genuinely
        idempotent on id (the contract its docstring promises)."""
        from fichero.models.knowledge import KnowledgeEntity, EntityType

        first = KnowledgeEntity(
            canonical_name="Quibdó",
            entity_type=EntityType.location,
            description="initial",
        )
        db.save(first)

        # Modify in place and re-save with the same id — must update,
        # not crash with a PK violation, not duplicate.
        first.description = "updated description"
        first.aliases = ["Kibdo"]
        db.save(first)

        rows = db.query(KnowledgeEntity, entity_type=EntityType.location)
        assert len(rows) == 1, "save with same id must update, not duplicate"
        assert rows[0].id == first.id
        assert rows[0].description == "updated description"
        assert rows[0].aliases == ["Kibdo"]

        # A fresh instance with the SAME id (the live #1120 crash path)
        # must also succeed via the ON CONFLICT update path.
        same_id_new_instance = KnowledgeEntity(
            id=first.id,
            canonical_name="Quibdó",
            entity_type=EntityType.location,
            description="re-created with same id",
        )
        db.save(same_id_new_instance)

        rows = db.query(KnowledgeEntity, entity_type=EntityType.location)
        assert len(rows) == 1
        assert rows[0].description == "re-created with same id"


class TestTwoStageKGWrite:
    """#1248: two-stage extraction must write KnowledgeEntity + KnowledgeClaim
    rows just like the oneshot path.  Pre-fix _run_two_stage returned without
    touching the DB."""

    @pytest.fixture
    def folder_doc(self, db):
        doc = Document(name="TwoStageFolder", path="/ts/folder", doc_type=DocType.folder)
        db.save(doc)
        return doc

    @pytest.mark.asyncio
    async def test_two_stage_writes_kg_entity_and_claim(
        self, db, test_package, folder_doc
    ):
        from fichero.workflows.tools.extract_all import (
            _EntitiesOnly, _EntityOnly, _EntityClaims, _SVOClaim,
        )
        from fichero.llm import LLMConfig

        llm = LLMConfig(provider="apple", model="apple/default")

        stage1_result = _EntitiesOnly(
            people=[_EntityOnly(name="María Josefa", aliases=[], entity_type="person")],
            places=[],
            organizations=[],
            dates=[],
            events=[],
        )
        stage2_result = _EntityClaims(
            subject="María Josefa",
            claims=[
                _SVOClaim(
                    subject="María Josefa",
                    verb="signed",
                    object="the deed",
                    source_text="María Josefa signed the deed in 1842.",
                )
            ],
        )

        call_count = {"n": 0}

        async def fake_chat_structured(**kwargs):
            call_count["n"] += 1
            schema = kwargs.get("schema")
            if schema is _EntitiesOnly:
                return stage1_result
            return stage2_result

        with patch(
            "fichero.workflows.tools.extract_all.chat_structured_with_fallback",
            new=AsyncMock(side_effect=fake_chat_structured),
        ):
            state = {
                "library_path": str(test_package),
                "selected_doc_ids": [folder_doc.id],
            }
            result = await __import__(
                "fichero.workflows.tools.extract_all", fromlist=["extract_all"]
            ).extract_all(
                inputs={"text": "María Josefa signed the deed in 1842.", "extraction_mode": "twostage"},
                state=state,
                llm_config=llm,
            )

        # KG entity written
        people = db.query(KnowledgeEntity, entity_type=EntityType.person)
        assert len(people) >= 1, "two-stage must write KnowledgeEntity rows"
        names = {e.canonical_name for e in people}
        assert "María Josefa" in names

        # Provenance claim attached to the container
        claims = db.query(KnowledgeClaim, source_document_id=folder_doc.id)
        assert len(claims) >= 1, "two-stage must write KnowledgeClaim rows"

        # kg_payload present in result
        assert "kg_payload" in result, "two-stage result must include kg_payload key"
        assert len(result["kg_payload"]) >= 1
