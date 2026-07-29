"""Unit tests for #1240: entity-type registry wired into extract_all runtime.

Covers:
- _load_registry_types returns only enabled non-builtin keys
- _build_instructions includes custom type guidance when types present
- _persist_additional_entities creates KnowledgeEntity rows with custom type key in metadata
"""

from __future__ import annotations

import pytest

from fichero_server.models.knowledge import (
    EntityResolutionRule,
    EntityResolutionRuleType,
    KnowledgeEntity,
    KnowledgeClaim,
    EntityType,
    LibraryEntityType,
)
from fichero_server.llm import LLMConfig
from fichero_server.models import DocType, Document
from fichero_server.workflows.tools import extract_all as extract_all_module
from fichero_server.workflows.tools.extract_all import (
    _load_registry_types,
    _build_instructions,
    _persist_additional_entities,
    _BUILTIN_EXTRACTION_KEYS,
    _normalize_custom_targets,
)


class TestLoadRegistryTypes:
    def test_returns_enabled_custom_types(self, db, test_package):
        lib_path = str(test_package)
        db.save(LibraryEntityType(library_id=lib_path, entity_type_key="crops", enabled=True))
        db.save(LibraryEntityType(library_id=lib_path, entity_type_key="manuscripts", enabled=True))

        result = _load_registry_types(db, lib_path)

        assert set(result) == {"crops", "manuscripts"}

    def test_disabled_types_excluded(self, db, test_package):
        lib_path = str(test_package)
        db.save(LibraryEntityType(library_id=lib_path, entity_type_key="crops", enabled=True))
        db.save(LibraryEntityType(library_id=lib_path, entity_type_key="inactive", enabled=False))

        result = _load_registry_types(db, lib_path)

        assert "inactive" not in result
        assert "crops" in result

    def test_builtin_keys_filtered_out(self, db, test_package):
        lib_path = str(test_package)
        for key in _BUILTIN_EXTRACTION_KEYS:
            db.save(LibraryEntityType(library_id=lib_path, entity_type_key=key, enabled=True))
        db.save(LibraryEntityType(library_id=lib_path, entity_type_key="crops", enabled=True))

        result = _load_registry_types(db, lib_path)

        # Result order is not guaranteed — assert membership only.
        assert set(result) == {"crops"}
        for key in _BUILTIN_EXTRACTION_KEYS:
            assert key not in result

    def test_empty_library_path_returns_empty(self, db):
        assert _load_registry_types(db, "") == []

    def test_no_registry_entries_returns_empty(self, db, test_package):
        result = _load_registry_types(db, str(test_package))
        assert result == []


class TestBuildInstructions:
    def test_no_custom_types_produces_base_instructions(self):
        instructions = _build_instructions("English")
        assert "expert archivist" in instructions
        assert "additional_entities" not in instructions

    def test_custom_types_appended_to_instructions(self):
        instructions = _build_instructions("English", ["crops", "manuscripts"])
        assert "additional_entities" in instructions
        assert "crops" in instructions
        assert "manuscripts" in instructions

    def test_empty_custom_types_no_additional_section(self):
        instructions = _build_instructions("English", [])
        assert "additional_entities" not in instructions


class TestNormalizeCustomTargets:
    def test_accepts_list_and_dedupes_case_insensitive(self):
        result = _normalize_custom_targets(["Fruit", "fruit", "Quotations"])
        assert result == ["fruit", "quotations"]

    def test_accepts_csv_string(self):
        result = _normalize_custom_targets("fruit, quotations, methods")
        assert result == ["fruit", "quotations", "methods"]

    def test_filters_builtin_keys(self):
        result = _normalize_custom_targets(["people", "events", "fruit"])
        assert result == ["fruit"]


class TestPersistAdditionalEntities:
    def test_creates_entity_rows_with_custom_type_key(self, db, test_package):
        container_id = "test-container"
        _persist_additional_entities(
            db,
            {"crops": ["wheat", "corn"]},
            container_id,
        )

        entities = db.query(KnowledgeEntity, entity_type=EntityType.other)
        names = {e.canonical_name for e in entities}
        assert "wheat" in names
        assert "corn" in names

        for e in entities:
            if e.canonical_name in {"wheat", "corn"}:
                assert "crops" in e.metadata.get("custom_entity_type_keys", [])

    def test_skips_empty_names(self, db, test_package):
        _persist_additional_entities(db, {"crops": ["", "  ", "wheat"]}, "c")
        entities = db.query(KnowledgeEntity, entity_type=EntityType.other)
        assert len(entities) == 1
        assert entities[0].canonical_name == "wheat"

    def test_does_not_duplicate_existing_entity(self, db, test_package):
        existing = KnowledgeEntity(
            canonical_name="wheat",
            entity_type=EntityType.other,
            metadata={},
        )
        db.save(existing)

        _persist_additional_entities(db, {"crops": ["wheat"]}, "c")

        all_entities = db.query(KnowledgeEntity, canonical_name="wheat", entity_type=EntityType.other)
        assert len(all_entities) == 1
        # metadata updated on existing row
        assert "crops" in all_entities[0].metadata.get("custom_entity_type_keys", [])

    def test_multiple_types_persist_independently(self, db, test_package):
        _persist_additional_entities(
            db,
            {
                "crops": ["wheat"],
                "minerals": ["silver"],
            },
            "c",
        )

        entities = db.query(KnowledgeEntity, entity_type=EntityType.other)
        keys_by_name = {e.canonical_name: e.metadata.get("custom_entity_type_keys", []) for e in entities}
        assert "crops" in keys_by_name["wheat"]
        assert "minerals" in keys_by_name["silver"]

    def test_provenance_claim_links_entity_to_container(self, db, test_package):
        container_id = "doc-abc-123"
        _persist_additional_entities(db, {"crops": ["wheat"]}, container_id)

        claims = db.query(KnowledgeClaim, source_document_id=container_id)
        assert len(claims) >= 1
        claim = claims[0]
        assert claim.source_document_id == container_id
        assert claim.metadata.get("custom_entity_type_key") == "crops"

    def test_same_name_two_types_preserves_both_keys(self, db, test_package):
        # "wheat" appears under two custom types; both keys must be in the list.
        _persist_additional_entities(db, {"crops": ["wheat"]}, "c1")
        _persist_additional_entities(db, {"grains": ["wheat"]}, "c2")

        all_entities = db.query(KnowledgeEntity, canonical_name="wheat", entity_type=EntityType.other)
        assert len(all_entities) == 1
        keys = all_entities[0].metadata.get("custom_entity_type_keys", [])
        assert "crops" in keys
        assert "grains" in keys

    def test_suppress_rule_skips_custom_entity_and_claim(self, db, test_package):
        db.save(
            EntityResolutionRule(
                rule_type=EntityResolutionRuleType.suppress,
                match_canonical_name="wheat",
                match_entity_type=EntityType.other,
                reason="noise",
            )
        )

        _persist_additional_entities(db, {"crops": ["wheat"]}, "doc-suppressed")

        assert db.query(KnowledgeEntity, canonical_name="wheat", entity_type=EntityType.other) == []
        assert db.query(KnowledgeClaim, source_document_id="doc-suppressed") == []


class TestCustomEntityPerChildScope:
    """#1562 write-path: custom-registry entities extracted while cataloguing a
    FOLDER (or multi-page PDF) must carry the PER-CHILD document id on their
    provenance claim and source_document_ids — not the parent container id.

    Before the fix, `extract_all` merged `additional_entities` across all chunks
    and called `_persist_additional_entities` once with `container.id`, so every
    custom-entity claim landed on the folder. Selecting a single child then
    showed no per-child custom entities, and the parent could only ever show a
    flat folder-scoped blob rather than a true union compiled from descendants.
    """

    @pytest.mark.asyncio
    async def test_folder_catalogue_scopes_custom_entities_per_child(
        self, db, test_package, monkeypatch
    ):
        folder = Document(name="Folder", path="/tmp/f", doc_type=DocType.folder)
        page1 = Document(
            name="p1", path="/tmp/f/p1.png", doc_type=DocType.page, parent_id=None
        )
        page2 = Document(
            name="p2", path="/tmp/f/p2.png", doc_type=DocType.page, parent_id=None
        )
        page1.parent_id = folder.id
        page2.parent_id = folder.id
        db.save(folder)
        db.save(page1)
        db.save(page2)

        lib_path = str(test_package)
        db.save(LibraryEntityType(library_id=lib_path, entity_type_key="crops", enabled=True))
        db.save(LibraryEntityType(library_id=lib_path, entity_type_key="minerals", enabled=True))

        # Mock the LLM so each page yields a DIFFERENT custom entity: page1 ->
        # "wheat" (crops), page2 -> "silver" (minerals). The chunk text routes
        # which custom entity comes back, mirroring a real per-page extraction.
        async def fake_extract(**kwargs):
            prompt = kwargs.get("prompt", "")
            if "WHEAT" in prompt:
                additional = {"crops": ["wheat"]}
            elif "SILVER" in prompt:
                additional = {"minerals": ["silver"]}
            else:
                additional = {}
            return extract_all_module._Extraction(
                people=[],
                places=[],
                organizations=[],
                dates=[],
                events=[],
                quotes=[],
                keywords=[],
                additional_entities=additional,
            )

        monkeypatch.setattr(
            "fichero_server.workflows.tools.extract_all.chat_structured_with_fallback",
            fake_extract,
        )

        state = {
            "library_path": lib_path,
            "selected_doc_ids": [folder.id],
        }
        llm_config = LLMConfig(provider="openai", model="gpt-4o-mini")

        await extract_all_module.extract_all(
            inputs={
                "persist_kg": True,
                "extraction_mode": "oneshot",
                "records": [
                    {"doc_id": page1.id, "text": "Page one mentions WHEAT in the field."},
                    {"doc_id": page2.id, "text": "Page two mentions SILVER from the mine."},
                ],
            },
            state=state,
            llm_config=llm_config,
        )

        # Custom-entity provenance claims must be stamped per CHILD, not folder.
        folder_claims = db.query(KnowledgeClaim, source_document_id=folder.id)
        page1_claims = db.query(KnowledgeClaim, source_document_id=page1.id)
        page2_claims = db.query(KnowledgeClaim, source_document_id=page2.id)

        assert len(folder_claims) == 0, (
            "custom-entity provenance claims must attach to the per-child page "
            "doc, not the parent folder (#1562 write-path)"
        )
        p1_names = {c.subject_canonical for c in page1_claims}
        p2_names = {c.subject_canonical for c in page2_claims}
        assert "wheat" in p1_names
        assert "silver" in p2_names
        assert "silver" not in p1_names
        assert "wheat" not in p2_names

        # Entity rows accumulate the child doc id in source_document_ids.
        wheat = db.query(KnowledgeEntity, canonical_name="wheat", entity_type=EntityType.other)[0]
        silver = db.query(KnowledgeEntity, canonical_name="silver", entity_type=EntityType.other)[0]
        assert page1.id in (wheat.source_document_ids or [])
        assert page2.id in (silver.source_document_ids or [])
        assert folder.id not in (wheat.source_document_ids or [])

        # Read-side: selecting a single child shows only that child's custom
        # entity; the parent/folder compiles the union across descendants.
        from fichero_server.api.routes.claim.claims import _descendant_doc_ids

        page1_scope = _descendant_doc_ids(db, page1.id)
        folder_scope = _descendant_doc_ids(db, folder.id)

        def entities_for(scope):
            names = set()
            for ent in db.query(KnowledgeEntity, entity_type=EntityType.other):
                if scope.intersection(ent.source_document_ids or []):
                    names.add(ent.canonical_name)
            return names

        assert entities_for(page1_scope) == {"wheat"}
        assert entities_for(folder_scope) == {"wheat", "silver"}
