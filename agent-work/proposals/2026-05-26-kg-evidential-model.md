# KG Evidential Claim Model: Temporal, Spatial, Attribution, Corroboration

Date: 2026-05-26  
Issues: #1266 backend, #1267 visualization  
Scope: design proposal only; no product-code changes in this pass.

## Summary

Fichero already has the right spine for this: `KnowledgeClaim` is the atomic assertion, `KnowledgeClaimLink` can connect claims by relation type including `corroborates`, `duplicate_of`, `supports`, `derives_from`, `cites`, `follows`, and `caused_by`, and #1123 already added speaker/source attribution fields such as `speaker_name`, `speaker_entity_id`, `scribe_name`, `editor_name`, `quotation_kind`, `provenance_layer`, `source_language`, `translation_chain`, `audience`, `source_genre`, and `confidence_source`.

The proposal is to extend that spine with structured, multi-valued evidential dimensions rather than replacing it:

- Claim dates become typed ranges, not one scalar field.
- Claim locations become regions/sets/paths, not one point.
- Every dimension value carries `basis = asserted | source_anchored | inferred`, confidence, source anchor, and extraction note.
- Attribution becomes an ordered chain of roles: speaker/asserter, reporter, recorder/source-document, editor, translator, processor.
- Corroboration reuses dedup/merge plus `KnowledgeClaimLink`, so duplicate claims collapse into one canonical claim supported by multiple source anchors.

Important rule: `source_anchored` is its own basis. It is not the same as asserted evidence. If text says "the riot happened in 1925", that is asserted. If the text lacks a date but the source document is dated 1925, the derived event range is bounded by the source and tagged `source_anchored`, e.g. `end = 1925-12-31`, `open_start = true`, `basis = source_anchored`, `source_field = Document.source_metadata.issued`.

## Existing Surfaces To Preserve

Backend:

- `fichero-engine/src/fichero/knowledge_models.py`
  - `KnowledgeClaim` already has `time_start`, `time_end`, `time_precision`, `claim_recorded_at`, `claim_geo`, `claim_location`, `temporal_context`, `source_document_id`, `source_ids`, `source_page_labels`, `source_excerpt`, source span/bbox, SVO fields, and #1123 attribution fields.
  - `KnowledgeClaimLink` already supports claim-to-claim relationships and metadata.
  - `ClaimRelationType` already includes `corroborates`, `duplicate_of`, `derives_from`, `cites`, `follows`, and `caused_by`.
  - `GeoPoint` exists but is point/radius-oriented.
- `fichero-engine/src/fichero/models.py`
  - `Document` already has `source_metadata`, `source_authority`, and document-level `provenance_chain`.
- `fichero-engine/src/fichero/workflows/tools/_entity_writer.py`
  - `save_claim()` is the central claim write path.
  - It already dedups by source document/page/entity/text overlap.
  - It centralizes #1123 attribution heuristics and stamps `confidence_source`.

Frontend:

- Swift consumes OpenAPI-generated `Components.Schemas.KnowledgeClaim` and `KnowledgeEntity`.
- `OntologyBrowser` loads claims by entity via `entityService.listClaims`.
- `EntitySourceGroupsView` groups claims by source document/page and already displays `temporalContext`, `claimLocation`, and `speakerName`.
- `ClaimSummaryCard+Details` already opens source documents and shows evidence chain counts.
- Existing KG graph/focus-neighborhood views should become peers with new timeline/map views, not be replaced.

## 1. Data Model

### New Shared JSON Shapes

These should be Pydantic models in `knowledge_models.py`, but persisted as JSON/list fields on existing tables so 0.0.x avoids migrations. Add fields to the Pydantic models and let table creation for new libraries see them. For existing libraries, follow the project rule: update model + `_ensure_table`/create-table shape, never `ALTER`.

#### `EvidenceBasis`

```python
class EvidenceBasis(str, Enum):
    asserted = "asserted"
    source_anchored = "source_anchored"
    inferred = "inferred"
```

Definitions:

- `asserted`: explicitly stated in source text or directly curated by a human.
- `source_anchored`: not stated in the claim text, but bounded from source document metadata/provenance.
- `inferred`: inferred by a model/rule from claim text, neighboring claims, or graph context without a direct source metadata bound.

#### `EvidentialDateRange`

```python
class EvidentialDateRange(BaseModel):
    id: str = Field(default_factory=_new_id)
    start: str | None = None
    end: str | None = None
    open_start: bool = False
    open_end: bool = False
    circa: bool = False
    precision: str | None = None  # year | month | day | decade | century | range | unknown
    label: str | None = None
    basis: EvidenceBasis
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    source_document_id: str | None = None
    source_page_label: str | None = None
    source_field: str | None = None  # e.g. source_metadata.issued, provenance_chain[0].date
    source_excerpt: str | None = None
    source_char_start: int | None = None
    source_char_end: int | None = None
    rationale: str | None = None
    created_by: str = "extractor"
```

Examples:

- Asserted "in 1925": `start=1925-01-01`, `end=1925-12-31`, `precision=year`, `basis=asserted`.
- Source anchored publication date: `start=None`, `end=1925-12-31`, `open_start=True`, `basis=source_anchored`, `source_field=source_metadata.issued`, `rationale="event must be no later than source publication date"`.
- Circa source date: `start=1924-01-01`, `end=1926-12-31`, `circa=True`, `basis=source_anchored`.

#### `EvidentialPlace`

```python
class PlaceGeometryType(str, Enum):
    point = "point"
    region = "region"
    path = "path"
    set = "set"
    unknown = "unknown"

class EvidentialPlace(BaseModel):
    id: str = Field(default_factory=_new_id)
    label: str
    geometry_type: PlaceGeometryType = PlaceGeometryType.unknown
    places: list[str] = Field(default_factory=list)  # named set/path members
    lat: float | None = Field(default=None, ge=-90.0, le=90.0)
    lon: float | None = Field(default=None, ge=-180.0, le=180.0)
    precision_m: float | None = None
    bbox: list[float] | None = None  # [west, south, east, north]
    geojson: dict | None = None
    basis: EvidenceBasis
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    source_document_id: str | None = None
    source_page_label: str | None = None
    source_field: str | None = None
    source_excerpt: str | None = None
    rationale: str | None = None
    created_by: str = "extractor"
```

Location is deliberately not just `lat/lon`. A colonial route can be a path, a jurisdiction can be a region, and an uncertain location can be a named set.

#### `AttributionStep`

```python
class AttributionRole(str, Enum):
    asserter = "asserter"          # who said/claimed it
    reporter = "reporter"          # who reported another speaker's claim
    recorder = "recorder"          # scribe/source document as recording act
    editor = "editor"
    translator = "translator"
    extractor = "extractor"
    source_document = "source_document"

class AttributionStep(BaseModel):
    role: AttributionRole
    name: str | None = None
    entity_id: str | None = None
    document_id: str | None = None
    label: str | None = None
    basis: EvidenceBasis = EvidenceBasis.asserted
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    source_excerpt: str | None = None
    source_field: str | None = None
    order: int = 0
```

Example chain:

1. `asserter`: "witness Pedro", entity `E-Pedro`, basis asserted.
2. `reporter`: "official Juan", basis asserted or inferred.
3. `recorder`: "scribe unknown", source field `Document.provenance_chain`.
4. `source_document`: document id/page.
5. `extractor`: provider/model from existing `provider`, `model`.

This keeps who said it separate from who reported/recorded it.

#### `SourceSupport`

```python
class SourceSupport(BaseModel):
    source_document_id: str
    source_page_label: str | None = None
    source_excerpt: str | None = None
    source_char_start: int | None = None
    source_char_end: int | None = None
    source_bbox: list[float] | None = None
    support_basis: EvidenceBasis = EvidenceBasis.asserted
    support_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    date_values: list[EvidentialDateRange] = Field(default_factory=list)
    place_values: list[EvidentialPlace] = Field(default_factory=list)
    attribution_chain: list[AttributionStep] = Field(default_factory=list)
```

This is the per-source layer. The claim can have canonical aggregate dimensions, but source support preserves exactly what each source contributed.

### Exact New Fields

#### Net-new `KnowledgeClaim` fields

Add these fields to `KnowledgeClaim`:

```python
date_values: list[EvidentialDateRange] = Field(default_factory=list)
place_values: list[EvidentialPlace] = Field(default_factory=list)
attribution_chain: list[AttributionStep] = Field(default_factory=list)
source_supports: list[SourceSupport] = Field(default_factory=list)
corroboration_count: int = 1
corroborating_source_ids: list[str] = Field(default_factory=list)
evidential_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
evidential_confidence_source: str | None = None  # e.g. "single_source", "corroboration", "human_review"
```

Keep existing fields:

- `time_start`, `time_end`, `time_precision`: backward-compatible canonical/display projection. Populate from the highest-confidence `date_values[0]` for old clients.
- `claim_location`, `claim_geo`: backward-compatible projection from highest-confidence place.
- `speaker_name`, `speaker_entity_id`, `scribe_name`, `editor_name`, `audience`, `quotation_kind`, `provenance_layer`, `confidence_source`: keep and populate from `attribution_chain` where applicable.
- `source_document_id`, `source_ids`, `source_page_labels`, `source_excerpt`, source span/bbox: keep for old clients and source navigation.
- `confidence`: keep as the primary confidence, but define it as the blended claim-level confidence. Store the explanatory inputs in `evidential_confidence_*` and `source_supports`.

#### Net-new `KnowledgeEntity` fields

Entities need temporal/spatial dimensions too, but should not pretend entity facts are identical to claims. Add:

```python
date_values: list[EvidentialDateRange] = Field(default_factory=list)
place_values: list[EvidentialPlace] = Field(default_factory=list)
attribution_chain: list[AttributionStep] = Field(default_factory=list)
source_supports: list[SourceSupport] = Field(default_factory=list)
corroboration_count: int = 0
```

Reuse existing entity fields such as `canonical_name`, `entity_type`, `aliases`, `description`, `source_document_ids`/claim-derived source grouping if present. Do not add scalar `lat/lon` as the primary entity location; if needed, expose a backward-compatible computed/projection field later.

### Table Creation / 0.0.x No-Migration Rule

Implementation should follow the project rule from #1266:

- Add fields to Pydantic models.
- Update the table creation path used for fresh libraries / `_ensure_table`-style setup to include the new JSON/list columns.
- Never run `ALTER TABLE` in 0.0.x.
- Existing libraries will have null/missing columns until rebuilt or migrated in a later release; API serializers must tolerate absence and default to `[]`/`None`.

## 2. Source-Anchored Inference In The Pipeline

### Where It Runs

Run source anchoring in the claim write pipeline, not as a UI-only derivation.

Recommended staging:

1. Extraction tools (`extractors.py`, `extract_all.py`) continue to emit asserted dates/places when the text contains them.
2. `_entity_writer.save_claim()` remains the central normalization/stamping point.
3. Add a helper near `_entity_writer.save_claim()`:

```python
derive_evidential_dimensions(
    db,
    claim_text,
    source_document_id,
    asserted_date_values,
    asserted_place_values,
    source_excerpt,
) -> tuple[list[EvidentialDateRange], list[EvidentialPlace], list[SourceSupport]]
```

4. The helper loads the source `Document`.
5. If asserted date/place exists, preserve as `basis=asserted`.
6. If missing, inspect source document metadata/provenance:
   - `Document.source_metadata` bibliographic dates: `issued`, `created`, `date`, `year`.
   - `Document.provenance_chain` steps: earliest recorded/filed/copied/scanned date with action semantics.
   - `Document.source_metadata` place fields or `Document.metadata` place/geocode fields if present.
   - source document entity/type if folder/page hierarchy already carries location.
7. Derive bounded values:
   - source publication/creation date gives an event upper bound unless source genre implies contemporaneous recording.
   - archival filing date gives `event_date <= filed_date` with lower bound open.
   - scan/access dates should not anchor event dates, only recorded/access provenance.
   - source place gives a source provenance place, not necessarily event place, unless source genre/metadata marks origin/site.
8. Stamp `basis=source_anchored`, `source_field`, `source_document_id`, confidence, and rationale.

### Provenance Stamping

For every derived value:

- `basis`: `source_anchored`.
- `confidence`: lower than asserted by default, e.g. 0.45-0.65 depending on source field strength.
- `source_field`: exact field path used, such as `source_metadata.issued` or `provenance_chain[0].date`.
- `rationale`: short human-readable reason.
- `source_supports[]`: includes both the claim source excerpt and the anchoring field.
- Existing `confidence_source`: use `source_anchored` or `corroboration` when that dominates.

### Corroboration / Dedup Path

Current `save_claim()` dedups within the same source/page/entity/text overlap. Extend the dedup/merge layer in phases:

1. Preserve current source-local dedup.
2. Add cross-source canonical matching by normalized SVO + entity IDs + predicate canonical + normalized object + compatible date/place ranges.
3. If the new claim is the same as an existing claim from another source:
   - Do not create a duplicate canonical claim.
   - Append/merge a `SourceSupport`.
   - Add the source doc id to `source_ids` / `corroborating_source_ids`.
   - Increment `corroboration_count`.
   - Create or update `KnowledgeClaimLink(relation_type=corroborates)` from the source-specific evidence claim if a separate row exists, or store the support directly if no separate row is created.
   - Recompute `confidence` with a transparent formula and set `confidence_source="corroboration"`.

Do not use source anchoring as strong corroboration by itself. Two source-anchored dates from related documents should raise confidence less than two asserted dates from independent sources.

## 3. OpenAPI Round Trip

Because the Swift app uses generated OpenAPI types, the JSON shapes must be explicit Pydantic fields, not arbitrary `metadata`.

Serialization shape on `KnowledgeClaim`:

```json
{
  "id": "claim-1",
  "text": "Pedro filed the petition.",
  "time_start": "1820-01-01",
  "time_end": "1820-12-31",
  "time_precision": "year",
  "date_values": [
    {
      "start": "1820-01-01",
      "end": "1820-12-31",
      "circa": false,
      "basis": "asserted",
      "confidence": 0.82,
      "source_document_id": "doc-1",
      "source_excerpt": "in 1820 Pedro filed..."
    }
  ],
  "place_values": [
    {
      "label": "Popayan jurisdiction",
      "geometry_type": "region",
      "bbox": [-77.2, 2.1, -76.2, 3.0],
      "basis": "source_anchored",
      "confidence": 0.55,
      "source_field": "source_metadata.place"
    }
  ],
  "attribution_chain": [
    {"role": "asserter", "name": "Pedro", "basis": "asserted", "confidence": 0.8, "order": 0},
    {"role": "reporter", "name": "court clerk", "basis": "source_anchored", "confidence": 0.6, "order": 1},
    {"role": "source_document", "document_id": "doc-1", "label": "Letter One", "order": 2}
  ],
  "source_supports": [
    {
      "source_document_id": "doc-1",
      "source_page_label": "3",
      "support_basis": "asserted",
      "support_confidence": 0.82,
      "date_values": [],
      "place_values": []
    }
  ],
  "corroboration_count": 2,
  "corroborating_source_ids": ["doc-1", "doc-7"],
  "confidence": 0.87,
  "confidence_source": "corroboration"
}
```

Frontend compatibility:

- Old UI can continue to read `timeStart/timeEnd/timePrecision`, `claimLocation`, `claimGeo`, `speakerName`.
- New UI reads `dateValues`, `placeValues`, `attributionChain`, `sourceSupports`, `corroborationCount`.
- Basis values should be generated as Swift enums where possible.
- If OpenAPI generator flattens nested additionalProperties poorly, keep these as explicitly typed Pydantic models and avoid `dict[str, Any]` except for `geojson`.

API route implications:

- `/api/claims` list/detail returns the new fields by default.
- Entity inspector responses include the new fields through embedded `KnowledgeClaim`.
- Evidence-chain endpoint should add `source_supports` and `attribution_chain`, not just source/related counts.
- Patch endpoints should eventually allow human override for dimension values. For 0.0.3, keep writes in backend extraction path and expose read-only fields first.

## 4. Frontend Visualization Plan (#1267)

### Views

Add a KG visualization suite as another mode/tab in the KnowledgeGraph area:

- Graph: existing graph/focus-neighborhood.
- Timeline: new claim/entity temporal view.
- Map: new spatial view.
- Source groups / speaker comparison: existing supporting panels.

### Timeline

Data:

- Use scoped claim/entity query, returning `dateValues`.
- Scope options: page, document, folder, library.
- Page/doc/folder scope should reuse existing source document filters and include-descendants behavior.

Rendering:

- Date range as horizontal span from `start` to `end`.
- Open-ended range fades toward the open edge.
- `circa` range uses soft/blurred boundary or dotted cap.
- Instant/day event renders as narrow marker.
- Multi-valued claim renders stacked mini-spans in the same lane or a collapsed marker with count.
- Corroboration count affects marker weight/badge.

Basis styling:

- `asserted`: solid stroke/fill.
- `source_anchored`: hatched or ghosted fill, visible "anchored" badge on hover/selection.
- `inferred`: dashed outline.
- Low confidence: lower opacity.

Interaction:

- Click selects claim/entity and sends the same selection state used by focus-neighborhood.
- Selection opens provenance drawer:
  - date/place value
  - basis
  - confidence
  - source field/excerpt
  - attribution chain
  - corroborating sources
- Brushing a time range filters graph/map/source groups.
- Graph selection filters timeline to connected neighborhood.

Implementation:

- Custom SwiftUI `Canvas` or lane layout for ranges.
- Avoid marketing-style hero/card layout; this is an inspector/work tool.
- Keep dense, sortable list fallback for accessibility and exact date review.

### MapKit Map

Data:

- Use `placeValues`.
- Point: `lat/lon`.
- Region: `bbox` or `geojson` polygon where available.
- Path: ordered `places` or `geojson` LineString.
- Set: multiple named places, optionally clustered.

Rendering:

- Point pins for exact points.
- Circles for `precision_m`.
- Rect/polygon overlays for regions.
- Polylines for paths/itineraries.
- Multi-place claims cluster with count badge.

Basis styling mirrors timeline:

- `asserted`: solid marker/overlay.
- `source_anchored`: hatched/outlined/ghosted overlay.
- `inferred`: dashed overlay.

Interaction:

- Selecting a map feature selects the claim/entity globally.
- Map viewport filters timeline and graph.
- Claim graph focus-neighborhood can highlight spatially related claims.
- Scope control filters to page/doc/folder/library.

### Cross-Filtering With Existing KG Graph

Use one shared selection/filter state:

- `selectedClaimId`
- `selectedEntityId`
- `selectedSourceDocumentId`
- `timeFilter: EvidentialDateRange?`
- `placeFilter: EvidentialPlace?`
- `basisFilter: Set<EvidenceBasis>`
- `scope: page | document | folder | library`

Graph/focus-neighborhood:

- Existing graph remains the relationship topology view.
- Timeline/map become evidence projections of the same selected claims/entities.
- Focus-neighborhood should accept incoming filters, not own a separate copy.

Entity/source panels:

- `EntitySourceGroupsView` can add compact badges beside each clause:
  - date span
  - place
  - basis icon
  - corroboration count
- `SpeakerComparisonView` should group by `attributionChain.first(role=.asserter)` while falling back to `speakerName`.

## 5. Phased Implementation Breakdown

### Phase 1 — Backend Schema + Contract (backend lane)

Files:

- `fichero-engine/src/fichero/knowledge_models.py`
- DB table creation / model registration path for fresh libraries.
- `fichero-engine/tests/unit/test_knowledge_models.py`
- OpenAPI sync artifacts.

Tasks:

- Add shared Pydantic models/enums.
- Add net-new fields to `KnowledgeClaim` and `KnowledgeEntity`.
- Ensure empty/default values round-trip as `[]`, not `null`, where arrays are expected.
- Keep old scalar fields populated for compatibility.
- Add tests for OpenAPI schema shape and Pydantic serialization.

Dependencies:

- None, but should land before extraction and UI work.

### Phase 2 — Source-Anchored Inference (backend lane)

Files:

- `fichero-engine/src/fichero/workflows/tools/_entity_writer.py`
- Extraction tests around `save_claim`.

Tasks:

- Add `derive_evidential_dimensions`.
- Convert existing `time_start/time_end/time_precision` args into `date_values` with `basis=asserted`.
- Convert existing `claim_location/claim_geo` when present into `place_values`.
- If missing, derive source-anchored ranges/places from `Document.source_metadata` and `Document.provenance_chain`.
- Stamp `SourceSupport`.
- Keep `time_*`, `claim_location`, `claim_geo` projections.

Dependencies:

- Phase 1.

### Phase 3 — Corroboration Merge (backend lane)

Files:

- `_entity_writer.py`
- possible small helper in `fichero-engine/src/fichero/kg/`
- claim link tests.

Tasks:

- Extend dedup beyond same source/page.
- Merge source supports for same canonical claim.
- Create/update `KnowledgeClaimLink(relation_type=corroborates)` where needed.
- Recompute confidence and `confidence_source`.
- Preserve source-specific evidence and avoid duplicate canonical claims.

Dependencies:

- Phase 1; can run after or alongside Phase 2 if interfaces are stable.

### Phase 4 — API Read Surfaces (backend/API lane)

Files:

- `api/routes/claims.py`
- entity inspector / evidence-chain routes.
- OpenAPI artifacts.

Tasks:

- Ensure claims, entity inspector, evidence chain expose the new fields.
- Add filters for `basis`, date range, place/region if practical.
- Keep source/document navigation intact.

Dependencies:

- Phase 1, preferably Phase 2.

### Phase 5 — Timeline UI (#1267, SwiftUI lane)

Files:

- New SwiftUI timeline view under `Views/KnowledgeGraph/`.
- Shared KG selection/filter state.
- Tests for state reducers/builders where logic is separable.

Tasks:

- Render date ranges/spans.
- Basis/confidence styling.
- Selection and provenance drawer.
- Cross-filter with graph and source groups.

Dependencies:

- Phase 4 OpenAPI fields.

### Phase 6 — MapKit UI (#1267, SwiftUI lane)

Files:

- New MapKit KG map view under `Views/KnowledgeGraph/`.
- Shared KG selection/filter state.

Tasks:

- Render point/region/path/set locations.
- Basis/confidence styling.
- Cross-filter with graph/timeline.
- Scope-aware page/doc/folder/library filtering.

Dependencies:

- Phase 4; can parallelize with Phase 5 after shared state is agreed.

### Phase 7 — Human Curation / Overrides (backend + SwiftUI)

Tasks:

- Add patch endpoint for evidential dimensions.
- UI editor for changing basis/confidence/ranges.
- Mark human changes with `basis=asserted` only when the human is asserting, otherwise `created_by=human_review` and preserve original basis.
- Mutation log before/after snapshots should capture edits.

Dependencies:

- Phases 1-6.

## Suggested Lane Assignments

- `gpt` backend lane: Phase 1 schema/contract, Phase 2 source anchoring, Phase 3 corroboration merge.
- `sonnet`/manager lane: review data-model fit, coordinate OpenAPI sync, enforce no migration rule.
- SwiftUI frontend lane: Phase 5 timeline and Phase 6 MapKit map after backend contract lands.
- Review lane: independent audit of source-anchored semantics, especially to prevent UI conflating `asserted` and `source_anchored`.

## Open Questions

1. Which `Document.source_metadata` keys are canonical for source dates/places? The design should define a priority list before implementation.
2. Should source-anchored place default to source provenance place for all genres, or only for known place-bearing genres such as deeds, maps, reports, and local petitions?
3. Does the system keep source-specific duplicate claim rows plus a canonical merged claim, or only one canonical claim with `source_supports`? I recommend one canonical claim plus source supports, with `KnowledgeClaimLink` used when separate analytical claims remain.
4. How should confidence blend corroboration? A simple first pass: max asserted confidence plus a capped corroboration bonus, reduced for source-anchored/inferred supports.
5. Should date/place extraction use deterministic regex/geocoder first, then LLM fallback, or rely on the existing extraction node output first? I recommend deterministic normalization after LLM extraction.

## Acceptance Criteria For The Future Implementation

- A claim can carry multiple date/place values, each with basis and confidence.
- Source-anchored values are serialized distinctly and rendered differently from asserted values.
- A source-dated document can bound an undated claim without pretending the date was in the claim text.
- Speaker/reporter/recorder/source are represented as an ordered chain.
- Multiple sources strengthen one claim through support/corroboration, not duplicate rows.
- Swift generated types expose the new fields without reaching into `metadata`.
- Timeline and map can filter and select the same claim/entity IDs used by the existing KG graph.
