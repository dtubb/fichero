"""Unit tests for #1240: entity-type registry wired into extract_all runtime.

Covers:
- _load_registry_types returns only enabled non-builtin keys
- _build_instructions includes custom type guidance when types present
- _persist_additional_entities creates KnowledgeEntity rows with custom type key in metadata
"""

from __future__ import annotations

import pytest

from fichero.knowledge_models import KnowledgeEntity, KnowledgeClaim, EntityType, LibraryEntityType
from fichero.workflows.tools.extract_all import (
    _load_registry_types,
    _build_instructions,
    _persist_additional_entities,
    _BUILTIN_EXTRACTION_KEYS,
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
