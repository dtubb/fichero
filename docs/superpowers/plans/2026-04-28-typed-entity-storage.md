# Typed Entity Storage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire catalogue extractors (`extractors.py`) and the catalogue reducer (`catalogue.py`) to write `KnowledgeEntity` + `KnowledgeClaim` rows into the existing KG layer instead of opaque `Artifact(data=json)` blobs. Inspector reads from `/api/entities` and `/api/claims` to render structured per-type views.

**Architecture:** The backend KG layer (`knowledge_models.py`, `api/routes/entities.py`, `api/routes/claims.py`) already exists with full CRUD, alias resolution, and dedup machinery. This plan **does not build new tables or models** — it connects the catalogue extraction pipeline to those existing models. People/places/organizations/events/concepts become `KnowledgeEntity` rows; dates and event mentions become `KnowledgeClaim` rows scoped to documents; free-form summaries stay as `Artifact` rows.

**Tech Stack:** FastAPI + Pydantic + DuckDB (backend), SwiftUI (frontend), OpenAPI generator for client.

**Reference:** `docs/architecture/typed_entity_storage.md` §0 (revised plan post-audit).

---

## File structure

### Files to modify

- `fichero-api/src/fichero/workflows/tools/extractors.py` — refactor `_run_extractor` to write KG rows, not Artifact JSON, for structured types.
- `fichero-api/src/fichero/workflows/tools/catalogue.py` — the reducer reads claims/entities instead of re-deriving from text; closes #727.
- `fichero-api/src/fichero/resources/default_workflows/catalogue.json` — drop archive-specific sections from defaults, add places/organizations.
- `fichero-api/src/fichero/resources/default_workflows/catalogue_composable.json` — same; closes #726.
- `fichero-swiftui/fichero-swiftui/Views/Library/DocumentInspector/DocumentInspectorArtifactsTab.swift` — read from `/api/entities` + `/api/claims` for structured types; keep current path for free-form.

### Files to create

- `fichero-api/src/fichero/workflows/tools/_entity_writer.py` — small module: `_upsert_entity(name, type, db)` + `_save_claim(text, doc_id, entity_ids, db)` helpers. Imported by `extractors.py` and `catalogue.py`.
- `fichero-api/tests/unit/workflows/test_entity_writer.py` — round-trip tests for the helpers.
- `fichero-api/tests/unit/workflows/test_extractor_kg_integration.py` — extractor → KG row tests.
- `fichero-swiftui/fichero-swiftui/Views/Library/DocumentInspector/EntityListView.swift` — generic per-type Inspector view; one impl, parameterized by EntityType.

### Files to read (no changes, just reference)

- `fichero-api/src/fichero/knowledge_models.py` — KnowledgeEntity, KnowledgeClaim, EntityType enum
- `fichero-api/src/fichero/api/routes/entities.py` — existing endpoints
- `fichero-api/src/fichero/api/routes/claims.py` — existing endpoints

---

## Phase 1 — Entity writer helpers + tests

### Task 1: Create `_entity_writer.py` skeleton

**Files:**
- Create: `fichero-api/src/fichero/workflows/tools/_entity_writer.py`
- Test: `fichero-api/tests/unit/workflows/test_entity_writer.py`

- [ ] **Step 1: Write the failing test for `_upsert_entity` (new entity case)**

```python
# fichero-api/tests/unit/workflows/test_entity_writer.py
import pytest
from fichero.knowledge_models import KnowledgeEntity, EntityType
from fichero.workflows.tools._entity_writer import upsert_entity


class TestUpsertEntity:
    def test_creates_new_entity_when_absent(self, db):
        entity_id = upsert_entity(
            db, canonical_name="María Angel", entity_type=EntityType.person
        )
        loaded = db.get(KnowledgeEntity, entity_id)
        assert loaded.canonical_name == "María Angel"
        assert loaded.entity_type == EntityType.person
```

- [ ] **Step 2: Run test to verify it fails**

```bash
PYTHONPATH=fichero-api/src .venv/bin/pytest \
  fichero-api/tests/unit/workflows/test_entity_writer.py::TestUpsertEntity::test_creates_new_entity_when_absent -v
```

Expected: FAIL with `ModuleNotFoundError: fichero.workflows.tools._entity_writer`.

- [ ] **Step 3: Write minimal implementation**

```python
# fichero-api/src/fichero/workflows/tools/_entity_writer.py
"""Helpers for writing KnowledgeEntity and KnowledgeClaim rows from catalogue
extractors. Centralizes the upsert + claim save pattern so each extractor
doesn't reimplement it.
"""

from __future__ import annotations

import logging
from typing import Optional

from fichero.db import Database
from fichero.knowledge_models import (
    EntityType,
    KnowledgeEntity,
    KnowledgeClaim,
    ClaimType,
)

logger = logging.getLogger(__name__)


def upsert_entity(
    db: Database,
    canonical_name: str,
    entity_type: EntityType,
    aliases: Optional[list[str]] = None,
    description: Optional[str] = None,
) -> str:
    """Look up entity by (canonical_name, entity_type); create if missing.

    Returns the entity ID. Idempotent — calling twice with same args reuses
    the existing row.
    """
    existing = db.query(KnowledgeEntity, canonical_name=canonical_name, entity_type=entity_type)
    if existing:
        return existing[0].id
    entity = KnowledgeEntity(
        canonical_name=canonical_name,
        entity_type=entity_type,
        aliases=aliases or [],
        description=description,
    )
    db.save(entity)
    return entity.id
```

- [ ] **Step 4: Run test to verify it passes**

```bash
PYTHONPATH=fichero-api/src .venv/bin/pytest \
  fichero-api/tests/unit/workflows/test_entity_writer.py::TestUpsertEntity::test_creates_new_entity_when_absent -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add fichero-api/src/fichero/workflows/tools/_entity_writer.py \
        fichero-api/tests/unit/workflows/test_entity_writer.py
git commit -m "feat(kg): add upsert_entity helper for catalogue extractors (#728)"
```

### Task 2: Idempotency — calling upsert twice reuses entity

**Files:**
- Modify: `fichero-api/tests/unit/workflows/test_entity_writer.py`

- [ ] **Step 1: Write the failing test**

```python
def test_idempotent_returns_same_id_on_repeat(self, db):
    id1 = upsert_entity(db, canonical_name="María Angel", entity_type=EntityType.person)
    id2 = upsert_entity(db, canonical_name="María Angel", entity_type=EntityType.person)
    assert id1 == id2
    # Only one row in DB
    rows = db.query(KnowledgeEntity, canonical_name="María Angel", entity_type=EntityType.person)
    assert len(rows) == 1
```

- [ ] **Step 2: Run test to verify it passes**

Run: same pytest command targeting `test_idempotent_returns_same_id_on_repeat`.
Expected: PASS (the implementation already handles this).

- [ ] **Step 3: Commit**

```bash
git add fichero-api/tests/unit/workflows/test_entity_writer.py
git commit -m "test(kg): assert upsert_entity idempotent on repeat call (#728)"
```

### Task 3: Add `save_claim` helper

**Files:**
- Modify: `fichero-api/src/fichero/workflows/tools/_entity_writer.py`
- Modify: `fichero-api/tests/unit/workflows/test_entity_writer.py`

- [ ] **Step 1: Write the failing test**

```python
class TestSaveClaim:
    def test_creates_claim_with_entity_links(self, db, sample_document):
        from fichero.workflows.tools._entity_writer import save_claim
        entity_id = upsert_entity(
            db, canonical_name="Juan Pérez", entity_type=EntityType.person
        )
        claim_id = save_claim(
            db,
            text="Juan Pérez signed the deed on 1931-08-03",
            source_document_id=sample_document.id,
            entity_ids=[entity_id],
            source_excerpt="...the deed was signed...",
        )
        loaded = db.get(KnowledgeClaim, claim_id)
        assert loaded.source_document_id == sample_document.id
        assert entity_id in loaded.entity_ids
        assert loaded.claim_type == ClaimType.fact
```

- [ ] **Step 2: Run test to verify it fails**

```bash
PYTHONPATH=fichero-api/src .venv/bin/pytest \
  fichero-api/tests/unit/workflows/test_entity_writer.py::TestSaveClaim -v
```

Expected: FAIL — `ImportError: cannot import name 'save_claim'`.

- [ ] **Step 3: Implement**

```python
# Append to fichero-api/src/fichero/workflows/tools/_entity_writer.py

def save_claim(
    db: Database,
    text: str,
    source_document_id: str,
    entity_ids: Optional[list[str]] = None,
    source_excerpt: Optional[str] = None,
    claim_type: ClaimType = ClaimType.fact,
    confidence: float = 0.5,
    metadata: Optional[dict] = None,
) -> str:
    """Save a KnowledgeClaim. Returns the claim ID.

    Claims are document-scoped textual assertions. Linked to entities via
    `entity_ids`. Free-form `text` is the claim itself; `source_excerpt`
    is the literal passage from the source document.
    """
    claim = KnowledgeClaim(
        text=text,
        source_document_id=source_document_id,
        entity_ids=entity_ids or [],
        source_excerpt=source_excerpt,
        claim_type=claim_type,
        confidence=confidence,
        metadata=metadata or {},
    )
    db.save(claim)
    return claim.id
```

- [ ] **Step 4: Run tests to verify pass**

```bash
PYTHONPATH=fichero-api/src .venv/bin/pytest \
  fichero-api/tests/unit/workflows/test_entity_writer.py -v
```

Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add fichero-api/src/fichero/workflows/tools/_entity_writer.py \
        fichero-api/tests/unit/workflows/test_entity_writer.py
git commit -m "feat(kg): add save_claim helper for document-scoped claims (#728)"
```

---

## Phase 2 — Refactor extractors to write KG rows

### Task 4: Add entity_type mapping per section

**Files:**
- Modify: `fichero-api/src/fichero/workflows/tools/extractors.py:91`

- [ ] **Step 1: Augment `_SECTIONS` with `entity_type` field**

Each entry gains a key mapping the section to an `EntityType` (or `None` for date-style claims with no entity).

```python
# In _SECTIONS, add to each entry:
{
    "name": "people_extract",
    "display": "Extract People",
    "artifact": "people",
    "entity_type": EntityType.person,   # NEW
    ...
},
{
    "name": "dates_extract",
    "display": "Extract Dates",
    "artifact": "dates",
    "entity_type": None,                # NEW — dates are claims, not entities
    ...
},
# repeat for events (event), keywords (concept), places (location, NEW), organizations (organization, NEW)
```

Drop entries for `rivers_extract`, `mines_extract`, `properties_extract`, `legal_references_extract` — closes #726.

Add new entries for `places_extract` (entity_type=location) and `organizations_extract` (entity_type=organization).

- [ ] **Step 2: Add the `EntityType` import at top of file**

```python
from fichero.knowledge_models import EntityType
```

- [ ] **Step 3: Run existing tests — they should still pass (no behavioral change)**

```bash
PYTHONPATH=fichero-api/src .venv/bin/pytest fichero-api/tests/unit/workflows/ -v
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add fichero-api/src/fichero/workflows/tools/extractors.py
git commit -m "feat(kg): annotate extractor sections with EntityType (#728)"
```

### Task 5: Refactor `_run_extractor` to write KG rows for structured types

**Files:**
- Modify: `fichero-api/src/fichero/workflows/tools/extractors.py:287` (`_run_extractor`)
- Test: `fichero-api/tests/unit/workflows/test_extractor_kg_integration.py` (new)

- [ ] **Step 1: Write the failing integration test**

```python
# fichero-api/tests/unit/workflows/test_extractor_kg_integration.py
import pytest
from unittest.mock import patch, AsyncMock
from fichero.knowledge_models import KnowledgeEntity, KnowledgeClaim, EntityType


class TestPeopleExtractorKGIntegration:
    @pytest.mark.asyncio
    async def test_writes_entity_and_claim_rows(self, db, sample_document, llm_config):
        """People extractor produces entity + claim rows, not artifacts."""
        from fichero.workflows.tools.extractors import _run_extractor, _SECTIONS

        people_section = next(s for s in _SECTIONS if s["name"] == "people_extract")
        fake_response = '{"personas_clave": [{"nombre": "Juan Pérez", "contexto": "deed signer"}]}'

        with patch("fichero.workflows.tools.extractors.chat", new=AsyncMock(return_value=fake_response)):
            state = {"library_path": str(db.path), "selected_doc_ids": [sample_document.id]}
            result = await _run_extractor(people_section, {"text": "..."}, state, llm_config)

        # One entity row created
        people = db.query(KnowledgeEntity, entity_type=EntityType.person)
        assert len(people) == 1
        assert people[0].canonical_name == "Juan Pérez"

        # One claim row links person → document
        claims = db.query(KnowledgeClaim, source_document_id=sample_document.id)
        assert len(claims) == 1
        assert people[0].id in claims[0].entity_ids
```

- [ ] **Step 2: Run test to verify it fails**

```bash
PYTHONPATH=fichero-api/src .venv/bin/pytest \
  fichero-api/tests/unit/workflows/test_extractor_kg_integration.py -v
```

Expected: FAIL — extractor still writes `Artifact`, no entity rows.

- [ ] **Step 3: Refactor `_run_extractor`**

After the existing JSON parse step, replace the artifact save block with:

```python
# extractors.py around line 360 (after `items` is parsed)
from fichero.workflows.tools._entity_writer import upsert_entity, save_claim

# Save KG rows for structured types
if container and library_path and section.get("entity_type") is not None:
    db = db_manager.get_database(library_path)
    entity_type = section["entity_type"]
    for item in items:
        # Item shape varies per section. Build canonical_name + context.
        canonical = item.get("nombre") or item.get("name") or ""
        context = item.get("contexto") or item.get("context") or ""
        if not canonical:
            continue
        entity_id = upsert_entity(
            db,
            canonical_name=canonical,
            entity_type=entity_type,
            aliases=item.get("ortografias_alternativas") or item.get("alternative_spellings") or [],
            description=context or None,
        )
        save_claim(
            db,
            text=f"{canonical}: {context}" if context else canonical,
            source_document_id=container.id,
            entity_ids=[entity_id],
            source_excerpt=context,
        )

# Date-style sections (entity_type is None): claims only, no entities
elif container and library_path and section.get("entity_type") is None:
    db = db_manager.get_database(library_path)
    for item in items:
        date_text = item.get("fecha", "")
        normalized = item.get("fecha_normalizada", "")
        context = item.get("contexto", "")
        text = f"{normalized or date_text}: {context}" if context else (normalized or date_text)
        save_claim(
            db,
            text=text,
            source_document_id=container.id,
            source_excerpt=context,
            metadata={"date_text": date_text, "date_normalized": normalized},
        )

# Markdown artifact write (existing) — keep for now; remove in Phase 3.
```

- [ ] **Step 4: Run integration test**

```bash
PYTHONPATH=fichero-api/src .venv/bin/pytest \
  fichero-api/tests/unit/workflows/test_extractor_kg_integration.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add fichero-api/src/fichero/workflows/tools/extractors.py \
        fichero-api/tests/unit/workflows/test_extractor_kg_integration.py
git commit -m "feat(kg): extractors write KnowledgeEntity + KnowledgeClaim rows (#728)"
```

### Task 6: Idempotency — second run on same doc doesn't duplicate entities

**Files:**
- Modify: `fichero-api/tests/unit/workflows/test_extractor_kg_integration.py`

- [ ] **Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_second_run_reuses_entities_creates_new_claims(self, db, sample_document, llm_config):
    """Running the extractor twice on the same doc should reuse entities but
    create new claims (provenance trail of multiple runs)."""
    from fichero.workflows.tools.extractors import _run_extractor, _SECTIONS

    people_section = next(s for s in _SECTIONS if s["name"] == "people_extract")
    fake_response = '{"personas_clave": [{"nombre": "Juan Pérez", "contexto": "deed signer"}]}'

    with patch("fichero.workflows.tools.extractors.chat", new=AsyncMock(return_value=fake_response)):
        state = {"library_path": str(db.path), "selected_doc_ids": [sample_document.id]}
        await _run_extractor(people_section, {"text": "..."}, state, llm_config)
        await _run_extractor(people_section, {"text": "..."}, state, llm_config)

    # Still one entity (canonical_name + entity_type uniqueness)
    people = db.query(KnowledgeEntity, entity_type=EntityType.person)
    assert len(people) == 1

    # But two claims — one per run, both pointing at the same entity
    claims = db.query(KnowledgeClaim, source_document_id=sample_document.id)
    assert len(claims) == 2
    assert all(people[0].id in c.entity_ids for c in claims)
```

- [ ] **Step 2: Run test**

Expected: PASS (upsert_entity is already idempotent; save_claim always creates new).

- [ ] **Step 3: Commit**

```bash
git add fichero-api/tests/unit/workflows/test_extractor_kg_integration.py
git commit -m "test(kg): assert extractor idempotent on entities, appends claims (#728)"
```

---

## Phase 3 — Drop Artifact write path for structured types

### Task 7: Remove markdown artifact write for structured types

**Files:**
- Modify: `fichero-api/src/fichero/workflows/tools/extractors.py:362-385` (artifact save block)

- [ ] **Step 1: Write the test that asserts no artifact is created for structured types**

```python
@pytest.mark.asyncio
async def test_no_artifact_row_for_structured_types(self, db, sample_document, llm_config):
    from fichero.workflows.tools.extractors import _run_extractor, _SECTIONS
    from fichero.models import Artifact

    people_section = next(s for s in _SECTIONS if s["name"] == "people_extract")
    fake_response = '{"personas_clave": [{"nombre": "Juan Pérez"}]}'

    with patch("fichero.workflows.tools.extractors.chat", new=AsyncMock(return_value=fake_response)):
        state = {"library_path": str(db.path), "selected_doc_ids": [sample_document.id]}
        await _run_extractor(people_section, {"text": "..."}, state, llm_config)

    # No "people" artifact row — KG rows replace it
    artifacts = db.query(Artifact, document_id=sample_document.id, artifact_type="people")
    assert len(artifacts) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Expected: FAIL — current code still writes a markdown artifact.

- [ ] **Step 3: Remove the artifact save in `_run_extractor`**

In `extractors.py`, delete the existing block:

```python
# DELETE:
if container and library_path:
    try:
        db = db_manager.get_database(library_path)
        artifact = Artifact(
            document_id=container.id,
            artifact_type=section["artifact"],
            content=markdown,
            data={"items": items} if items else None,
            ...
        )
        db.save(artifact)
        ...
```

Keep the markdown rendering — it still becomes the `text` return value so downstream nodes (like the catalogue tool, until Phase 6 closes #727) can read it.

- [ ] **Step 4: Run all extractor tests**

```bash
PYTHONPATH=fichero-api/src .venv/bin/pytest \
  fichero-api/tests/unit/workflows/ -v
```

Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add fichero-api/src/fichero/workflows/tools/extractors.py \
        fichero-api/tests/unit/workflows/test_extractor_kg_integration.py
git commit -m "refactor(kg): drop Artifact write for structured types (#728)"
```

---

## Phase 4 — Default workflow JSONs updated

### Task 8: Generify catalogue.json + catalogue_composable.json

**Files:**
- Modify: `fichero-api/src/fichero/resources/default_workflows/catalogue.json`
- Modify: `fichero-api/src/fichero/resources/default_workflows/catalogue_composable.json`
- Modify: `fichero-api/tests/unit/workflows/test_default_workflows.py`

- [ ] **Step 1: Update test locks**

```python
def test_composable_has_generic_extractors(default_workflow_jsons):
    composable = default_workflow_jsons["catalogue_composable"]
    node_tools = {n["tool"] for n in composable["nodes"]}
    expected_extractors = {
        "people_extract", "places_extract", "organizations_extract",
        "events_extract", "dates_extract", "keywords_extract",
    }
    assert expected_extractors.issubset(node_tools)
    forbidden = {"rivers_extract", "mines_extract", "properties_extract", "legal_references_extract"}
    assert not (forbidden & node_tools)
```

- [ ] **Step 2: Run to verify it fails**

```bash
PYTHONPATH=fichero-api/src .venv/bin/pytest \
  fichero-api/tests/unit/workflows/test_default_workflows.py::test_composable_has_generic_extractors -v
```

Expected: FAIL.

- [ ] **Step 3: Edit `catalogue_composable.json`**

Remove these node entries: `rivers`, `mines`, `properties`, `legal`.
Add these new nodes: `places` (tool: `places_extract`), `organizations` (tool: `organizations_extract`).
Remove edges referencing the dropped nodes; add edges from `aggregate.text → places.text` and `aggregate.text → organizations.text`.

- [ ] **Step 4: Edit `catalogue.json`**

Same: drop archive sections from any internal config that references them. Catalogue prompt schema should reference only the generic sections.

- [ ] **Step 5: Run tests**

```bash
PYTHONPATH=fichero-api/src .venv/bin/pytest fichero-api/tests/unit/workflows/ -v
```

Expected: all green, including new lock test.

- [ ] **Step 6: Commit**

```bash
git add fichero-api/src/fichero/resources/default_workflows/catalogue.json \
        fichero-api/src/fichero/resources/default_workflows/catalogue_composable.json \
        fichero-api/tests/unit/workflows/test_default_workflows.py
git commit -m "feat(workflow): generify default catalogue workflows (#726)"
```

### Task 9: Register new places + organizations extractors

**Files:**
- Modify: `fichero-api/src/fichero/workflows/tools/extractors.py:91` (_SECTIONS)

- [ ] **Step 1: Add `places_extract` and `organizations_extract` to `_SECTIONS`**

```python
{
    "name": "places_extract",
    "display": "Extract Places",
    "artifact": "places",
    "entity_type": EntityType.location,
    "icon": "mappin.and.ellipse",
    "color": "green",
    "schema_key": "lugares",
    "item_shape": '{"nombre": "...", "ortografias_alternativas": ["..."], "contexto": "..."}',
    "instruction": (
        "List every named place — cities, countries, regions, addresses, "
        "geographic features. Canonical name + alternative spellings + context."
    ),
},
{
    "name": "organizations_extract",
    "display": "Extract Organizations",
    "artifact": "organizations",
    "entity_type": EntityType.organization,
    "icon": "building.2",
    "color": "indigo",
    "schema_key": "organizaciones",
    "item_shape": '{"nombre": "...", "ortografias_alternativas": ["..."], "contexto": "..."}',
    "instruction": (
        "List every organization — companies, institutions, agencies, "
        "governmental bodies. Name + aliases + context."
    ),
},
```

Drop the four archive-specific entries (`rivers_extract`, `mines_extract`, `properties_extract`, `legal_references_extract`).

- [ ] **Step 2: Run tool registry tests + composable workflow test**

```bash
PYTHONPATH=fichero-api/src .venv/bin/pytest fichero-api/tests/unit/workflows/ -v
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add fichero-api/src/fichero/workflows/tools/extractors.py
git commit -m "feat(workflow): add places + organizations, drop archive-specific (#726)"
```

---

## Phase 5 — Inspector reads from /api/entities + /api/claims

### Task 10: Swift entity service wrapper

**Files:**
- Modify: `fichero-swiftui/fichero-swiftui/Services/` — add `EntityServiceGenerated.swift` if absent (likely OpenAPI-generated; verify)

- [ ] **Step 1: Verify the generated client has entities endpoints**

Check that `fichero-swiftui/fichero-api-client/Sources/FicheroAPIClient/Client.swift` has methods like `listEntitiesApiEntitiesGet`. Run:

```bash
grep -c "listEntitiesApiEntitiesGet\|listClaimsApiClaimsGet" \
  fichero-swiftui/fichero-api-client/Sources/FicheroAPIClient/Client.swift
```

Expected: > 0. If 0, regenerate the OpenAPI client:

```bash
./fichero-api/scripts/sync_openapi_schema.sh
```

- [ ] **Step 2: Add a service wrapper** (if not present)

Pattern: copy `WorkflowServiceGenerated.swift`'s shape. Methods:
- `listEntities(documentId: String?) async throws -> [Entity]`
- `listClaims(sourceDocumentId: String) async throws -> [Claim]`

- [ ] **Step 3: Build to verify**

```bash
xcodebuild -project fichero-swiftui/fichero-swiftui.xcodeproj \
  -scheme Fichero -destination 'platform=macOS,arch=arm64' \
  -derivedDataPath /tmp/fichero-build-728 -skipPackagePluginValidation build 2>&1 | tail -3
```

Expected: BUILD SUCCEEDED.

- [ ] **Step 4: Commit**

```bash
git add fichero-swiftui/fichero-swiftui/Services/EntityServiceGenerated.swift
git commit -m "feat(swift): EntityServiceGenerated for /api/entities + /api/claims (#728)"
```

### Task 11: EntityListView per-type Swift view

**Files:**
- Create: `fichero-swiftui/fichero-swiftui/Views/Library/DocumentInspector/EntityListView.swift`

- [ ] **Step 1: Create the view**

```swift
import SwiftUI
import FicheroAPIClient

/// Inspector tab content showing entities of a given type for a document.
/// Reads from the existing /api/entities + /api/claims layer.
struct EntityListView: View {
    let documentId: String
    let entityType: String   // "person", "location", "organization", "event", "concept"

    @EnvironmentObject var entityService: EntityServiceGenerated
    @State private var entities: [Entity] = []
    @State private var isLoading = false

    var body: some View {
        Group {
            if isLoading {
                ProgressView()
            } else if entities.isEmpty {
                ContentUnavailableView("No \(entityType)s extracted", systemImage: "person.2.slash")
            } else {
                List(entities) { entity in
                    VStack(alignment: .leading, spacing: 4) {
                        Text(entity.canonicalName).font(.headline)
                        if !entity.aliases.isEmpty {
                            Text("Also: \(entity.aliases.joined(separator: ", "))")
                                .font(.caption).foregroundStyle(.secondary)
                        }
                        if let desc = entity.description, !desc.isEmpty {
                            Text(desc).font(.callout).lineLimit(3)
                        }
                    }
                    .padding(.vertical, 4)
                }
            }
        }
        .task { await load() }
    }

    private func load() async {
        isLoading = true
        defer { isLoading = false }
        do {
            entities = try await entityService.listEntities(documentId: documentId, entityType: entityType)
        } catch {
            entities = []
        }
    }
}
```

- [ ] **Step 2: Add SwiftUI #Preview** with mock entities so it renders in the canvas without a backend.

- [ ] **Step 3: Build**

Expected: BUILD SUCCEEDED.

- [ ] **Step 4: Commit**

```bash
git add fichero-swiftui/fichero-swiftui/Views/Library/DocumentInspector/EntityListView.swift
git commit -m "feat(inspector): EntityListView reads from /api/entities (#728)"
```

### Task 12: Wire EntityListView into DocumentInspectorArtifactsTab

**Files:**
- Modify: `fichero-swiftui/fichero-swiftui/Views/Library/DocumentInspector/DocumentInspectorArtifactsTab.swift`

- [ ] **Step 1: Replace the markdown-artifact loader with EntityListView for structured types**

For artifact types in {`people`, `places`, `organizations`, `events`, `keywords`}, render `EntityListView(documentId: doc.id, entityType: <mapped>)`. For free-form (`summary`, `catalogue`), keep current ArtifactPanel rendering.

- [ ] **Step 2: Build**

Expected: BUILD SUCCEEDED.

- [ ] **Step 3: Three-leg check**

```bash
swiftlint lint fichero-swiftui/fichero-swiftui/
xcodebuild ... build
xcodebuild ... test
```

Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add fichero-swiftui/fichero-swiftui/Views/Library/DocumentInspector/DocumentInspectorArtifactsTab.swift
git commit -m "feat(inspector): wire structured-type panels to entity API (#728)"
```

---

## Phase 6 — Catalogue reducer consumes claims (closes #727)

### Task 13: Catalogue tool reads claims for the document

**Files:**
- Modify: `fichero-api/src/fichero/workflows/tools/catalogue.py:312` (`catalogue` async function)
- Test: `fichero-api/tests/unit/workflows/test_catalogue_consumes_claims.py` (new)

- [ ] **Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_catalogue_groups_existing_claims_by_entity_type(db, sample_document, llm_config):
    """When entity rows exist for the doc, catalogue tool builds the unified
    artifact from those rows instead of running a second extraction LLM call.
    """
    from fichero.workflows.tools._entity_writer import upsert_entity, save_claim
    from fichero.workflows.tools.catalogue import catalogue
    from fichero.knowledge_models import EntityType

    # Pre-seed: 2 people, 1 place, 2 dates
    p1 = upsert_entity(db, "Juan Pérez", EntityType.person)
    p2 = upsert_entity(db, "María Angel", EntityType.person)
    place = upsert_entity(db, "Medellín", EntityType.location)
    save_claim(db, "Juan Pérez signed", sample_document.id, [p1])
    save_claim(db, "María Angel objected", sample_document.id, [p2])
    save_claim(db, "Medellín hearing", sample_document.id, [place])
    save_claim(db, "1930-05-12: deed", sample_document.id, [])
    save_claim(db, "1931-08-03: appeal", sample_document.id, [])

    state = {"library_path": str(db.path), "selected_doc_ids": [sample_document.id]}
    # Don't mock chat — assert it isn't called when claims exist
    with patch("fichero.workflows.tools.catalogue.chat") as mock_chat:
        result = await catalogue({"text": ""}, state, llm_config)
        # No re-extraction LLM call when structured data is present
        assert mock_chat.call_count <= 1  # at most one call for resumen narrative

    # Resulting catalogue artifact has the structured findings
    from fichero.models import Artifact
    artifacts = db.query(Artifact, document_id=sample_document.id, artifact_type="catalogue")
    assert len(artifacts) == 1
    data = artifacts[0].data
    assert len(data.get("personas_clave", [])) == 2
    assert len(data.get("lugares", [])) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Expected: FAIL — current catalogue tool runs full LLM extraction.

- [ ] **Step 3: Refactor `catalogue` async function**

Read claims/entities for the document; build the 9-section data structure from them; only call LLM for the `resumen` narrative.

```python
# Pseudocode for the refactored body:
db = db_manager.get_database(library_path)
claims = db.query(KnowledgeClaim, source_document_id=container.id)

# Group claims by entity type (via entity_ids → entities)
sections = _group_claims_into_sections(db, claims)

# Build the 9-section data dict directly
data = {
    "personas_clave": sections.get("person", []),
    "lugares": sections.get("location", []),
    "organizaciones": sections.get("organization", []),
    "eventos_clave": sections.get("event", []),
    "palabras_clave": sections.get("concept", []),
    "fechas": sections.get("dates", []),  # claims with no entity_ids
    # Summary: only this requires an LLM call
    "resumen": await _generate_summary(text, sections, llm_config),
}

# Save the unified catalogue artifact (markdown rendering + structured data)
markdown = _render_markdown(data)
artifact = Artifact(
    document_id=container.id, artifact_type="catalogue",
    content=markdown, data=data, ...
)
db.save(artifact)
```

- [ ] **Step 4: Run test to verify pass**

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add fichero-api/src/fichero/workflows/tools/catalogue.py \
        fichero-api/tests/unit/workflows/test_catalogue_consumes_claims.py
git commit -m "feat(kg): catalogue reducer consumes existing claims (#727)"
```

### Task 14: Three-leg check + close issues

- [ ] **Step 1: Full backend test suite**

```bash
PYTHONPATH=fichero-api/src .venv/bin/pytest fichero-api/tests/unit/ \
  --ignore=fichero-api/tests/unit/_archived -q
```

Expected: all pass (or only pre-existing failures).

- [ ] **Step 2: Backend lint**

```bash
ruff check fichero-api/src/
```

Expected: All checks passed.

- [ ] **Step 3: SwiftLint**

```bash
swiftlint lint fichero-swiftui/fichero-swiftui/
```

Expected: clean for files we touched.

- [ ] **Step 4: Xcode build**

```bash
xcodebuild -project fichero-swiftui/fichero-swiftui.xcodeproj \
  -scheme Fichero -destination 'platform=macOS,arch=arm64' \
  -derivedDataPath /tmp/fichero-build-728 -skipPackagePluginValidation build 2>&1 | tail -3
```

Expected: BUILD SUCCEEDED.

- [ ] **Step 5: Push and close issues**

```bash
git push origin 0.0.2

gh issue close 728 --comment "Shipped on 0.0.2 — extractors now write KnowledgeEntity + KnowledgeClaim rows, Inspector reads from /api/entities."
gh issue close 727 --comment "Shipped on 0.0.2 in catalogue refactor — catalogue tool consumes existing claims instead of re-extracting."
gh issue close 726 --comment "Shipped on 0.0.2 — composable defaults updated to people/places/organizations/events/dates/keywords; archive-specific dropped from defaults (still registered for power users)."
```

---

## Self-review notes

- **Spec coverage:** every section of `docs/architecture/typed_entity_storage.md` §0 has a corresponding task: helpers (Phase 1), extractor refactor (Phase 2), artifact drop (Phase 3), defaults (Phase 4), Inspector (Phase 5), catalogue reducer (Phase 6).
- **Apple Intelligence build-up workflow:** intentionally deferred to 0.0.3+ — depends on `chat()` provider routing for Apple, currently a no-op branch. Tracked separately.
- **Cross-doc UI:** "click name → all sources" deferred — backend already supports it via `/api/entities/{id}` + `/api/claims?entity_id=…`; UI wiring in 0.0.3+.
- **Type extensibility (#706 phase 3):** EntityType enum is fixed in 0.0.2; user-declared types in 0.0.3 either extends the enum at runtime or adds a sibling `CustomEntity` model.
- **No migration tooling:** library DB is wipeable per Daniel's call — pre-existing markdown artifacts of types `people/dates/...` will simply not appear in the new Inspector views; users re-run workflows to populate KG rows.
