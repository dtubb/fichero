(AI generated. Not reviewed.)

# Extensibility Guarantee

Issue: #1652

This backend treats new extraction outputs as additive in 0.0.x. The contract test is [test_extensibility_guarantee.py](fichero-engine/tests/contracts/test_extensibility_guarantee.py).

## Guaranteed additive extension points

- Entity-type registry:
  New entity-type keys are data in `ClassificationValue` plus `LibraryEntityType`, not new schema. The runtime registry loader accepts new keys with no table change. Today, extractor-emitted custom types persist on `KnowledgeEntity.metadata["custom_entity_type_keys"]` and use `entity_type=other` for the canonical row.
- SVO predicates:
  `KnowledgeClaim.predicate_verb` and related SVO fields are open strings, so new predicates do not require migrations.
- Artifact outputs:
  New extraction products land as new `Artifact.artifact_type` string values plus optional structured `Artifact.data`. No enum expansion or table migration is required.
- W3C / IIIF motivations:
  Annotation import stores motivations in free-form metadata such as `Annotation.metadata["w3c_motivation"]`, so new motivation values stay additive.
- Free-form metadata / additive fields on extensible rows:
  `Document`, `KnowledgeEntity`, `KnowledgeClaim`, `Annotation`, and `Note` all use `extra="allow"`, so newly added response fields do not break decode and survive model round-trip.
- No-migration schema growth in 0.0.x:
  `Database._ensure_table()` reconciles model fields against existing DuckDB tables and issues idempotent `ADD COLUMN` statements for missing declared fields. Adding a new declared field with a default does not require a hand-written migration.

## Current gaps

- `# TODO(#1652)` First-class `KnowledgeEntity.entity_type` values are still backed by the built-in `EntityType` enum. New library registry keys are additive for extraction and persistence via metadata, but they are not yet first-class `entity_type` values on the row itself.
- `# TODO(#1652)` First-class `KnowledgeClaim.quotation_kind` values are still backed by the built-in `QuotationKind` enum. New quote kinds would currently require a code/schema change rather than flowing as open data.

## What the contract test enforces

- Extensible models preserve unknown additive fields.
- `artifact_type` remains an open string and round-trips through persistence.
- New entity-type registry keys can be added without changing table shape.
- `_ensure_table()` upgrades an existing table to include newly declared model fields without a separate migration.
