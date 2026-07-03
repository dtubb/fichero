"""Contract tests for additive / no-migration extensibility guarantees (#1652)."""

from __future__ import annotations

import duckdb
from pathlib import Path

from fichero.db import Database
from fichero.knowledge_models import (
    Annotation,
    AnnotationKind,
    ClassificationDimension,
    ClassificationValue,
    EntityType,
    KnowledgeClaim,
    KnowledgeEntity,
    LibraryEntityType,
    Note,
)
from fichero.models import Artifact, Document
from fichero.workflows.tools.extract_all import _load_registry_types, _persist_additional_entities


def _column_names(db: Database, table_name: str) -> list[str]:
    rows = db.conn.execute(f'PRAGMA table_info("{table_name}")').fetchall()
    return [row[1] for row in rows]


def test_extensible_models_preserve_unknown_fields():
    """Unknown additive fields must survive decode/dump on extensible models."""

    models_and_payloads = [
        (
            Document,
            {
                "name": "Letter 14",
                "extension_probe": {"layer": "iiif"},
            },
        ),
        (
            KnowledgeEntity,
            {
                "canonical_name": "Pedro de Alcantara",
                "entity_type": EntityType.person,
                "extension_probe": {"importer": "marshall"},
            },
        ),
        (
            KnowledgeClaim,
            {
                "text": "Pedro petitioned the cabildo.",
                "source_document_id": "doc-1",
                "extension_probe": {"analysis": "sentiment"},
            },
        ),
        (
            Annotation,
            {
                "kind": AnnotationKind.note,
                "text": "Margin note",
                "extension_probe": {"w3c_motivation": ["commenting", "tagging"]},
            },
        ),
        (
            Note,
            {
                "body": "A zettel about the petition.",
                "extension_probe": {"workspace": "thesis"},
            },
        ),
    ]

    for model_cls, payload in models_and_payloads:
        model = model_cls.model_validate(payload)
        dumped = model.model_dump()

        assert model_cls.model_config.get("extra") == "allow"
        assert dumped["extension_probe"] == payload["extension_probe"]


def test_artifact_type_is_open_and_round_trips(db: Database):
    """New extraction outputs land as new artifact_type strings, not schema changes."""

    artifact = Artifact(
        document_id="doc-1",
        artifact_type="marginalia_sentiment",
        content="positive affect",
        data={
            "score": 0.82,
            "labels": ["marginalia", "sentiment"],
        },
    )

    db.save(artifact)
    loaded = db.get(Artifact, artifact.id)

    assert loaded is not None
    assert loaded.artifact_type == "marginalia_sentiment"
    assert loaded.data == artifact.data


def test_entity_type_registry_accepts_new_keys_without_schema_change(db: Database, test_package: Path):
    """A new entity-type key is data, not a new table/column."""

    db._ensure_table(ClassificationValue)
    db._ensure_table(LibraryEntityType)
    classification_columns_before = _column_names(db, "classificationvalues")
    library_type_columns_before = _column_names(db, "libraryentitytypes")

    db.save(
        ClassificationValue(
            dimension=ClassificationDimension.entity_type,
            key="plant_species",
            label="Plant Species",
        )
    )
    db.save(
        LibraryEntityType(
            library_id=str(test_package),
            entity_type_key="plant_species",
            enabled=True,
        )
    )

    registry_keys = _load_registry_types(db, str(test_package))
    _persist_additional_entities(db, {"plant_species": ["cassava"]}, "doc-1")

    classification_columns_after = _column_names(db, "classificationvalues")
    library_type_columns_after = _column_names(db, "libraryentitytypes")
    entities = db.query(KnowledgeEntity, canonical_name="cassava", entity_type=EntityType.other)

    assert "plant_species" in registry_keys
    assert classification_columns_after == classification_columns_before
    assert library_type_columns_after == library_type_columns_before
    assert len(entities) == 1
    assert "plant_species" in entities[0].metadata.get("custom_entity_type_keys", [])


def test_ensure_table_adds_missing_columns_for_existing_tables(tmp_path: Path):
    """0.0.x rule: adding a model field with a default must not require a migration."""

    db_path = tmp_path / "legacy.duckdb"
    legacy_conn = duckdb.connect(str(db_path))
    try:
        legacy_conn.execute(
            """
            CREATE TABLE artifacts (
                id VARCHAR,
                document_id VARCHAR,
                source_artifact_id VARCHAR,
                version INTEGER,
                artifact_type VARCHAR,
                content VARCHAR,
                PRIMARY KEY (id)
            )
            """
        )
    finally:
        legacy_conn.close()

    db = Database(db_path)
    artifact = Artifact(
        document_id="doc-legacy",
        artifact_type="places_mentioned",
        content="Quito; Popayan",
        data={"places": ["Quito", "Popayan"]},
        provider="test-provider",
        reviewed=True,
    )

    db.save(artifact)
    loaded = db.get(Artifact, artifact.id)
    columns = _column_names(db, "artifacts")
    db.close()

    assert loaded is not None
    assert loaded.data == {"places": ["Quito", "Popayan"]}
    assert loaded.provider == "test-provider"
    assert loaded.reviewed is True
    assert "data" in columns
    assert "provider" in columns
    assert "reviewed" in columns
