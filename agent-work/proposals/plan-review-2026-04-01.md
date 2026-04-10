# Plan Review — Fichero 0.0.2 Knowledge Graph
**Date:** 2026-04-01
**Plan:** `/Users/danieltubb/.claude/plans/frolicking-puzzling-cosmos.md`

---

## Summary

The current plan proposes "Backend Slice 2" - Knowledge Graph Inspector API with enhanced models (8 new enums, prediction models) and 8 new endpoints. Analysis reveals **7 critical issues** that should be addressed before implementation.

---

## Problems Found

### 1. Endpoint Structure Conflicts with REST Patterns
**Current State:**
- SwiftUI uses `APIClient` with generic REST methods
- Backend `knowledge_graph.py` router mounted at `/api/knowledge-graph`
- Existing endpoints: `/entities`, `/claims`, `/claims/{id}/links`, `/inclusion`

**Issue:**
- `/api/knowledge-graph/claims/search` vs existing `/api/knowledge-graph/claims` with query filters
- Inconsistent nesting: `/api/knowledge-graph/claims/{id}/sources` vs simpler patterns
- Missing Swift API endpoints in `APIEndpoints.swift`

**Impact:**
- SwiftUI cannot consume endpoints without `APIEndpoints.swift` entries
- 8 endpoints don't map cleanly to Swift's RESTful patterns
- Existing `list_claims` already supports filtering - plan duplicates functionality

### 2. Missing Swift Model Definitions
**Current State:**
- `knowledge_models.py` has existing enums and models
- Plan adds: `SourceType`, `ClaimType`, `EpistemicStatus`, `PredictionEntity`, etc.

**Issue:**
- Swift has no corresponding model types
- Plan says "Swift is dumb display" but `DocumentInspector` consumes `Document` model
- `KnowledgeClaim` in Swift must match Python model exactly for decoding

**Impact:**
- Swift `APIClient` fails to decode responses with `prediction: PredictionMetadata`
- Even partial data requires exact schema match on Swift side

### 3. No Data Migration Strategy
**Current State:**
- `KnowledgeClaim` has `source_document_id` (single string)
- Plan adds `source_ids: list[str]`, `source_page_labels: list[str]`, `source_languages: list[str]`

**Issue:**
- Existing claims have single source, new structure expects multiple
- No migration strategy for existing records
- No default values for `source_type` on existing records

**Impact:**
- Existing claims break when backend serializes with new `source_type` field
- Database migration needed to backfill `source_type = "document"`

### 4. Plan Endpoints Duplicate Existing Functionality
**Current State:**
Existing `/api/knowledge-graph/claims` already supports:
- `q`: text search
- `entity_id`: filter by entity
- `curation_state`: filter by status
- `source_document_id`: filter by document
- `scope_type` + `target_id`: folder/library scoping

**Issue:**
- Plan proposes `/claims/search` (duplicates existing filter)
- Plan proposes `/claims/by-source` (duplicates `source_document_id` filter)
- Plan proposes `/ontology/claims-by-entity` (duplicates `entity_id` filter)

**Impact:**
- API surface explosion without clear value
- Swift services duplicate logic for similar endpoints
- Test coverage splits between similar endpoints

### 5. Missing PyKEEN Implementation Details
**Issue:**
- No implementation details for PyKEEN integration
- How are predictions stored? (new table? serialized in metadata?)
- How are predictions trained? (online learning? batch retraining?)
- What's the API for applying a prediction?
- No error handling for missing PyKEEN dependency

**Impact:**
- Implementation stalled at "add 8 new endpoints" phase
- No test strategy for ML-based prediction endpoints
- No rollback path if PyKEEN models fail

### 6. OpenAPI Schema Generation Not Verified
**Issue:**
- No verification that OpenAPI schema exports new enums correctly
- No check that nested structures (`PredictionMetadata`) export correctly
- Swift `FicheroClient.swift` must match Python models exactly

**Impact:**
- OpenAPI schema may miss nested structures
- Swift client may decode incorrectly
- Type mismatches cause runtime crashes

### 7. Missing Test Strategy for New Filtering
**Issue:**
- Tests only validate happy paths
- No edge cases for new multi-source model
- No tests for prediction application

**Impact:**
- Runtime errors when Swift app uses new filters
- Incomplete test coverage delays release

---

## Proposed Changes

### A. Consolidate Endpoints (Replace 8 with 4-5)

**Existing endpoint extended with new filters:**
```
GET  /api/knowledge-graph/claims
   q: str
   claim_type: ClaimType          # fact|analysis|interpretation|argument|historiography|theory
   curation_state: ClaimCurationState  # unreviewed|shortlisted|curated|rejected
   epistemic_status: EpistemicStatus   # tentative|confirmed|rejected
   entity_id: str
   source_language: str
   source_type: SourceType
   scope_type: InclusionScopeType
   target_id: str
   next_logical_for: str          # get predictions for this claim
   page: int
   limit: int
```

**Additional endpoints:**
```
GET  /api/knowledge-graph/claims/{id}/sources    # resolve sources for a claim
GET  /api/knowledge-graph/predictions            # list predictions (review queue)
POST /api/knowledge-graph/predictions            # create prediction
POST /api/knowledge-graph/predictions/apply      # apply prediction to create claim
```

### B. Add Swift API Endpoints

```swift
// Add to fichero-swiftui/fichero-swiftui/Services/APIEndpoints.swift

enum KnowledgeGraphEndpoints {
    static let base = "/knowledge-graph"
    
    static let entities = "/knowledge-graph/entities"
    
    static let claims = "/knowledge-graph/claims"
    static func claim(_ id: String) -> String { "/knowledge-graph/claims/\(id)" }
    
    static let predictions = "/knowledge-graph/predictions"
    static let predictionsApply = "/knowledge-graph/predictions/apply"
    
    static func claimSources(_ id: String) -> String { "/knowledge-graph/claims/\(id)/sources" }
}
```

### C. Add Migration Versioning

```python
# In knowledge_models.py
class KnowledgeClaim(BaseModel):
    # ... existing fields ...
    migration_version: int = Field(default=0, ge=0)  # NEW
    
    @classmethod
    def migrate_from_v0(cls, claim: "KnowledgeClaim") -> "KnowledgeClaim":
        """Migrate legacy single-source claim to multi-source structure."""
        if claim.migration_version >= 1:
            return claim
        claim.source_ids = [claim.source_document_id]
        claim.source_types = [SourceType.document]
        claim.source_languages = [claim.language] if claim.language else []
        claim.migration_version = 1
        return claim
```

### D. Add Prediction Model

```python
class KnowledgePrediction(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="allow")
    
    id: str = Field(default_factory=_new_id)
    claim_id: str
    predicted_claim_text: str
    link_type: str  # next_logical, supports, contradicts, refines
    confidence: float
    model_name: str
    metadata: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.now)
```

### E. Add Verification Steps to Plan

```
6. Update OpenAPI schema and regenerate Swift client
   cd fichero-api
   ./scripts/sync_openapi_schema.sh
   # Verify new types in openapi.json:
   grep -A5 "SourceType" openapi.json
   grep -A10 "PredictionMetadata" openapi.json
   # Validate Swift compiles without errors
```

---

## Questions for Daniel

1. **Endpoint design**: Should I consolidate to existing `/claims` endpoint with filters, or keep separate endpoints as proposed?

2. **Swift integration**: Should Swift consume these endpoints directly, or through a dedicated `KnowledgeGraphService` wrapper?

3. **PyKEEN timeline**: Should predictions be implemented in phases (storage → simple heuristics → PyKEEN ML)?

4. **Migration**: Should existing claims get `migration_version=0` with legacy single-source structure, or should there be a one-time migration?

---

## Verdict: **Needs work**

### High-Priority Fixes Before Implementation
- [x] Endpoint structure consolidation
- [ ] Swift model generation strategy
- [ ] PyKEEN integration approach
- [ ] Migration strategy approval

### Ready to Implement After
- [ ] Endpoint structure approved
- [ ] Swift integration approach confirmed
- [ ] PyKEEN integration approach confirmed
- [ ] Migration strategy approved

---

## Implementation Order (After Approval)

1. **Update models** in `knowledge_models.py`
   - Add SourceType, ClaimType, EpistemicStatus enums
   - Add PredictionEntity, PredictionUncertaintySpan, PredictionLink models
   - Add PredictionMetadata model
   - Update KnowledgeClaim with new fields and migration_version
   - Add KnowledgePrediction model

2. **Update OpenAPI schema**
   - Run `./scripts/sync_openapi_schema.sh`
   - Verify schema exports all new types
   - Validate Swift client generation

3. **Add helper functions** in `knowledge_graph.py`
   - `_resolve_sources()` - resolve source IDs with language info
   - `_build_source_reference()` - single source resolution

4. **Add endpoints** in `knowledge_graph.py`
   - Extended `/claims` with new filters
   - `/claims/{id}/sources` - resolve sources for a claim
   - `/predictions` - list/create/apply predictions

5. **Add tests** in `test_knowledge_graph_api.py`
   - 13+ new test functions for all new functionality

6. **Swift integration**
   - Add API endpoints to `APIEndpoints.swift`
   - Add Swift types from OpenAPI (auto-generated)
   - Create KnowledgeGraphService wrapper

7. **Run quality checks**
   - `ruff check fichero-api/src/`
   - `.venv/bin/pytest fichero-api/tests/unit/`
   - `swiftlint lint fichero-swiftui/fichero-swiftui/`
