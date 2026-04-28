# Typed Entity Storage — Design

> **Status:** Design proposal. Open decisions marked **DECIDE**. Once approved, implementation plan moves to `docs/superpowers/plans/YYYY-MM-DD-typed-entity-storage.md`.
>
> **Goal milestone:** 0.0.2 (release-blocking — must land before users accumulate markdown-only artifact data that would need migration).
>
> **Author:** session 2026-04-28.

## 1. Why this exists

Today every catalogue extractor saves an `Artifact` with:
- `content`: a markdown rendering of what it found
- `data`: a JSON blob like `{"items": [{"name": "...", "context": "..."}]}`

That's an opaque blob from the database's point of view. We can grep markdown, but we can't:

- **Search**: "find all docs that mention a person whose name normalizes to *Angel*"
- **Cross-reference**: "click María Angel → see every document where she appears, with her dates and locations"
- **Build the KG**: the 0.2.x milestones (KG Entities, Claims, Ontology) need typed entity rows as substrate. Re-deriving them from markdown later means re-running LLM calls.
- **Export cleanly**: typed JSON → Zotero / RDF / Linked Open Data is one mapping; markdown → those is hand-written for every export target.

The fix: structured entity types live in their own DuckDB tables, queryable as relational data. Free-form artifacts (summary, narrative) keep their markdown shape. Extractors become *parsers* (LLM call → typed rows), not *artifact producers*; markdown becomes a *derived view* generated for display.

## 2. Scope

**In scope (0.0.2):**
- DuckDB schema for structured entity types: `people`, `dates`, `events`, `places`, `organizations`, `keywords`.
- Pydantic models per entity type.
- Extractor refactor: write to entity tables instead of artifact `data` JSON.
- Read API to query entities by document, by type, by content.
- Inspector rendering: typed views per entity (people list, date timeline, etc.) — minimum: render the structured data, no cross-doc linking yet.
- Migration: re-run extractors on existing artifacts, since extant markdown can't be parsed back into structured rows reliably.

**Out of scope (0.0.3+):**
- Cross-document entity links ("click name → see all docs mentioning"). Plumbing prepared, UI deferred.
- Entity deduplication ("M. Angel" = "María Angel"). Schema accommodates aliasing; matching algorithm is separate work.
- Apple Intelligence build-up extractor variant. Tracked separately (#727 follow-up).
- KG layers (Claims, Ontology, Predictions) — those are 0.2.x.

**Free-form artifacts stay as `Artifact` rows:**
- `summary`, `catalogue` (the unified narrative), any user-defined freeform types.
- These keep `content: markdown, data: optional dict` shape unchanged.

## 3. Open design decisions

For each: **DECIDE**, then I lock and proceed.

### 3.1 Schema topology — per-type tables vs polymorphic

**Option A — One table per entity type:**
```sql
CREATE TABLE people (id, document_id, run_id, name, alternative_spellings, context, …);
CREATE TABLE dates  (id, document_id, run_id, date_text, date_normalized, context, …);
CREATE TABLE events (id, document_id, run_id, description, context, …);
…
```

**Option B — One polymorphic table:**
```sql
CREATE TABLE entities (
  id, document_id, run_id,
  entity_type TEXT,    -- 'person' | 'date' | 'event' | …
  data JSON            -- type-specific shape
);
```

**Recommendation: Option A.** Per-type tables give us strongly-typed columns that DuckDB can index, range-query (dates), and join on. Type B is "JSON columns with a discriminator" — same opacity problem we're solving. The cost of A is more migrations when adding entity types; the win is real columnar SQL.

**DECIDE:** A / B / something else.

### 3.2 Foreign key model — entity → document directly, or entity → artifact → document

**Option A — Entity references document directly:**
```
entity_row.document_id → documents.id
```
The artifact (markdown rendering) is generated post-hoc and is optional.

**Option B — Entity references artifact, artifact references document:**
```
entity_row.artifact_id → artifacts.id → documents.id
```
Provenance: which extraction run produced this entity is linkable via the artifact.

**Option C — Both: entity has both `document_id` (denormalized for query speed) AND `artifact_id` (provenance):**
```
entity_row.document_id, entity_row.artifact_id (nullable)
```

**Recommendation: Option C.** Provenance matters (for re-extraction and trust), but most queries are "entities for this doc" — denormalizing avoids the artifact join. `artifact_id` nullable so entities can exist without an artifact (e.g. user-edited or manual entries).

**DECIDE:** A / B / C.

### 3.3 Should markdown artifacts coexist with entity rows?

When an extractor runs, it produces structured rows. Today it also writes a markdown artifact. Should it keep doing both?

**Option A — Drop the markdown artifact entirely.** Entity rows are the source of truth; render markdown on the fly when display needs it.

**Option B — Keep both: write entity rows AND a derived markdown artifact.** Inspector reads whichever it prefers.

**Option C — Keep markdown artifact only for "free-form" types (summary, catalogue narrative), drop it for structured types (people, dates, etc.).**

**Recommendation: Option C.** Structured types are queried; storing their markdown is duplication that drifts. Free-form types are the markdown blob — that's their nature. The Inspector picks the renderer based on `entity_type` (structured) or `artifact_type` (free-form).

**DECIDE:** A / B / C.

### 3.4 Migration of existing markdown artifacts

Existing user libraries have artifacts saved as markdown only. What happens when this lands?

**Option A — Re-extract on first inspector view of a folder.** Lazy migration; user pays one LLM call cost when they next open an inspector tab.

**Option B — One-shot migration tool / button: "Migrate to typed entities".** User runs it explicitly, sees progress, knows the cost.

**Option C — Accept legacy: pre-refactor artifacts stay markdown-only, render with old view; new runs produce entity rows.**

**Option D — Force re-run on app upgrade**: app boot detects old-format artifacts, prompts user.

**Recommendation: Option B.** Explicit user action means predictable LLM spend, no surprise costs. App detects unmigrated artifacts and shows a banner ("3 folders have legacy data — run migration to enable cross-doc search"). User clicks, sees per-folder progress, can pause/resume.

**DECIDE:** A / B / C / D.

### 3.5 Dedup strategy

Two artifacts mention "M. Angel" and "María Angel" — same person? When do we collapse?

**Option A — At save time:** every save runs a similarity check against existing rows; if matched, link as alias.

**Option B — At read time:** rows are saved as-is; a `canonical_id` field is computed lazily by a periodic job or on first cross-doc query.

**Option C — Punt entirely for 0.0.2:** schema accommodates aliases (`alternative_spellings: list`), but no automatic dedup. Cross-doc views show duplicates; user manually flags. Dedup algorithm is its own piece of work for 0.0.3+.

**Recommendation: Option C.** Dedup is a hard problem (LLM-assisted matching, name normalization, fuzzy compare). Schema must accommodate it (`alternative_spellings` list, optional `canonical_id` column for later) but the algorithm is out of scope. Ship the substrate; dedupe later.

**DECIDE:** A / B / C.

### 3.6 Where do entity types live (extensibility)?

Are entity types **hard-coded** (fixed set: people / dates / events / places / orgs / keywords) or **declarable** (users define new entity types like "ships" or "ranches")?

**Option A — Hard-coded.** Types are Pydantic classes shipped with the app. Adding a type = code change.

**Option B — Declarable in the workflow JSON.** Each extractor declares the columns it produces; the ORM/migration creates a table on first save. User-defined extractors get user-defined entity tables.

**Recommendation: Option A for 0.0.2.** Six known types is enough surface area. Option B is the natural 0.0.3+ extension once we see how the typed-entity layer is used.

**DECIDE:** A / B.

## 4. Locked-in shape (assuming recommendations above)

Given Options A / C / C / B / C / A, the architecture:

### 4.1 DuckDB schema

```sql
-- One table per structured entity type. Common columns first; type-specific after.

CREATE TABLE people (
  id TEXT PRIMARY KEY,
  document_id TEXT NOT NULL REFERENCES documents(id),
  artifact_id TEXT REFERENCES artifacts(id),  -- provenance, nullable
  run_id TEXT,
  -- type-specific:
  name TEXT NOT NULL,
  alternative_spellings JSON,  -- list[str]
  context TEXT,
  canonical_id TEXT,  -- for future dedup; nullable
  created_at TIMESTAMP NOT NULL DEFAULT now()
);
CREATE INDEX idx_people_document_id ON people(document_id);
CREATE INDEX idx_people_name ON people(name);

CREATE TABLE dates (
  id TEXT PRIMARY KEY,
  document_id TEXT NOT NULL REFERENCES documents(id),
  artifact_id TEXT,
  run_id TEXT,
  date_text TEXT NOT NULL,
  date_normalized TEXT,    -- 'YYYY-MM-DD' or 'YYYY-MM-DD/YYYY-MM-DD' for ranges
  context TEXT,
  created_at TIMESTAMP NOT NULL DEFAULT now()
);
CREATE INDEX idx_dates_document_id ON dates(document_id);
CREATE INDEX idx_dates_normalized ON dates(date_normalized);

CREATE TABLE events (
  id TEXT PRIMARY KEY,
  document_id TEXT NOT NULL,
  artifact_id TEXT,
  run_id TEXT,
  description TEXT NOT NULL,
  context TEXT,
  created_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE places (
  id TEXT PRIMARY KEY,
  document_id TEXT NOT NULL,
  artifact_id TEXT,
  run_id TEXT,
  name TEXT NOT NULL,
  alternative_spellings JSON,
  context TEXT,
  canonical_id TEXT,
  created_at TIMESTAMP NOT NULL DEFAULT now()
);
CREATE INDEX idx_places_name ON places(name);

CREATE TABLE organizations (
  id TEXT PRIMARY KEY,
  document_id TEXT NOT NULL,
  artifact_id TEXT,
  run_id TEXT,
  name TEXT NOT NULL,
  alternative_spellings JSON,
  context TEXT,
  canonical_id TEXT,
  created_at TIMESTAMP NOT NULL DEFAULT now()
);
CREATE INDEX idx_organizations_name ON organizations(name);

CREATE TABLE keywords (
  id TEXT PRIMARY KEY,
  document_id TEXT NOT NULL,
  artifact_id TEXT,
  run_id TEXT,
  keyword TEXT NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT now()
);
CREATE INDEX idx_keywords_keyword ON keywords(keyword);
```

Free-form artifacts (`summary`, `catalogue`, narrative) keep using the existing `artifacts` table.

### 4.2 Pydantic models

```python
# fichero-api/src/fichero/models.py — new section

class Person(BaseModel):
    id: str = Field(default_factory=_new_id)
    document_id: str
    artifact_id: str | None = None
    run_id: str | None = None
    name: str
    alternative_spellings: list[str] = Field(default_factory=list)
    context: str | None = None
    canonical_id: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)

class DateMention(BaseModel):
    id: str = Field(default_factory=_new_id)
    document_id: str
    artifact_id: str | None = None
    run_id: str | None = None
    date_text: str
    date_normalized: str | None = None
    context: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)

class EventMention(BaseModel):
    id: str = Field(default_factory=_new_id)
    document_id: str
    artifact_id: str | None = None
    run_id: str | None = None
    description: str
    context: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)

class Place(BaseModel):
    id: str = Field(default_factory=_new_id)
    document_id: str
    artifact_id: str | None = None
    run_id: str | None = None
    name: str
    alternative_spellings: list[str] = Field(default_factory=list)
    context: str | None = None
    canonical_id: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)

class Organization(BaseModel):
    id: str = Field(default_factory=_new_id)
    document_id: str
    artifact_id: str | None = None
    run_id: str | None = None
    name: str
    alternative_spellings: list[str] = Field(default_factory=list)
    context: str | None = None
    canonical_id: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)

class Keyword(BaseModel):
    id: str = Field(default_factory=_new_id)
    document_id: str
    artifact_id: str | None = None
    run_id: str | None = None
    keyword: str
    created_at: datetime = Field(default_factory=datetime.now)
```

### 4.3 Extractor refactor pattern

`extractors.py:_run_extractor` today does:
1. LLM call → JSON → list of items.
2. Save `Artifact(content=markdown, data={"items": items})`.

After refactor:
1. LLM call → JSON → list of items (unchanged).
2. **For structured types**: save N entity rows (one per item) + optionally a thin "extraction-run" Artifact for provenance.
3. **For free-form types**: save `Artifact(content=markdown, data=...)` as today.

The decision is keyed off the section's `entity_type`. Each section in `_SECTIONS` declares which entity model it produces; the save path branches on type.

### 4.4 API surface

```
GET  /api/entities/{type}?document_id=X&q=Y         # list entities by type for doc
GET  /api/entities/{type}/{id}                       # single entity
GET  /api/documents/{doc_id}/entities                # all entities for doc, grouped by type
PATCH /api/entities/{type}/{id}                      # user edit (correct a name, add alias)
DELETE /api/entities/{type}/{id}                     # user delete
```

Cross-doc query (deferred to 0.0.3 but the schema supports it):
```
GET /api/entities/{type}?q=Maria&library_path=...    # find across whole library
```

### 4.5 Inspector rendering

Per `entity_type`, Swift Inspector picks a view:
- `people` → table view: name, aliases pill, context tooltip. Clickable name (deferred: cross-doc search).
- `dates` → chronological list with normalized form on hover, original text below.
- `events` → bulleted list with context.
- `places`, `organizations` → same shape as people.
- `keywords` → tag cloud / chip row.
- Free-form artifacts (`summary`, `catalogue`) → existing markdown renderer.

Existing `DocumentInspectorArtifactsTab` becomes the entry point: for each entity type, query the typed API; for each free-form artifact, query the existing artifacts API.

### 4.6 Migration

UI affordance: a banner in the Library / Inspector when legacy artifacts exist:

> "5 folders have data from before typed entities. Run migration to enable cross-document search. Estimated: 12 LLM calls, ~$0.30."

Click → background job re-runs each extractor against the source transcripts → new entity rows → old artifacts marked `migrated=True` (kept for audit, hidden from UI by default).

## 5. Roadmap impact

Verified against GitHub milestones on 2026-04-28.

### Items that **collapse or move earlier**

- **#495 Release Gate 0.2.0 — KG Entities.** Gate text reads: *"After transcribing a document, extracted entities appear in the document inspector and sidebar."* That IS this design's deliverable. Shipping in 0.0.2 means 0.2.0's gate criteria are *already met* by the time we get there — the 0.2.0 milestone collapses to whatever's beyond entity storage (relationship graphs, cross-doc linking, dedup).
- **#706 Inspector V2 phase 3 (currently 0.0.3) — user-defined attribute schema.** This design ships hard-coded types (§3.6 Option A); phase 3 becomes the natural follow-up for user-declared types and stays in 0.0.3.
- **#497 Release Gate 0.2.2 — KG Claim Inspector.** A Claim joins Entity rows with provenance Artifacts; the substrate is ready after this work. Implementation moves from "build entity model + relationship model" to "build relationship model over existing entities" — net faster.
- **#498 Release Gate 0.2.3 — Ontology Browser.** Categories applied to Entity rows; substrate ready.
- **0.2.1 KG Claims List** — currently empty milestone, but the work is reachable immediately after this ships.

### Items that **don't change but are unblocked**

- **#481 Release Gate 0.0.3 — Search v1.** Text search hits transcripts; independent of entity tables. Stays as planned.
- **#482 Release Gate 0.0.4 — Search v2 (Filters + Layouts).** Entity-type filters (`person:Maria`, `date:1930-1940`) become possible immediately — an obvious next-quarter win without re-architecting.
- **#483 Release Gate 0.0.5 — Search v3 (Semantic Map + Saved).** Maps over typed entities; this design provides the substrate.

### Net roadmap effect

| Milestone | Before this design | After this design |
|---|---|---|
| 0.0.2 | Polish + release pipeline (~1 wk) | Polish + release pipeline + typed entity layer (~3-4 wks) |
| 0.0.3 | Search v1 + #706 phase 3 | Search v1 + #706 phase 3 (user-defined types) |
| 0.0.4 | Search v2 — filters | Search v2 + entity filters (richer) |
| 0.2.0 | Build KG Entities from scratch | **Gate already met — milestone shrinks or merges** |
| 0.2.1-0.2.3 | Builds on 0.2.0 | Builds on 0.0.2 — earlier start, less rework |

Net: 0.0.2 takes longer but 0.2.x ships earlier. Cumulative engineering shifts left, and we avoid the "extract twice" cost of having users accumulate markdown-only data through the 0.0.x → 0.2.x interim.

## 6. Implementation phases (proposed; locked after design approval)

**Phase 1 — Schema + Models (1-2 days)**
- DuckDB migration adding 6 tables.
- Pydantic models, `db.query/save` works for them.
- Tests: round-trip save/load per type.
- No extractor changes yet; no UI changes.

**Phase 2 — Extractor refactor (1-2 days)**
- `extractors.py:_run_extractor` writes entity rows for structured types.
- Existing `_SECTIONS` map to entity types; refactor declares this mapping.
- Tests: each extractor's run produces rows in the matching table.
- Markdown artifacts no longer written for structured types (per §3.3 Option C).

**Phase 3 — Read API (1 day)**
- New router: `entities.py`. Endpoints from §4.4 (single-doc surface only).
- Pydantic response models, OpenAPI regen.
- Tests: route handlers return correct shapes.

**Phase 4 — Inspector rendering (2-3 days)**
- Swift `DocumentInspector` reads entity API for each type.
- Per-type SwiftUI views (PeopleListView, DateTimelineView, etc.).
- Free-form artifacts unchanged.
- Tests: snapshot/preview tests per view.

**Phase 5 — Migration tool (1-2 days)**
- Detect legacy artifacts (no matching entity rows for the run_id).
- UI banner + migration button.
- Backend job: re-run extractors against source transcripts.
- Test: migrate a fixture library, verify entity rows appear.

**Phase 6 — Catalogue refactor (1 day)**
- `catalogue` tool reads entity rows for the doc instead of re-deriving.
- Composable workflow's catalogue node consumes structured outputs (closes #727).

**Total estimate:** 7-10 working days. 0.0.2 ship date moves out by ~2 weeks accordingly.

## 7. Risks

- **DuckDB JSON column quirks** for `alternative_spellings` — verify roundtrip behavior with our existing `db.py:save/query`.
- **Migration failures**: if the LLM call during re-extraction fails, partial entity tables. Need an idempotent re-run ("entities for run_id X exist? skip").
- **Extractor cache invalidation**: existing cache logic keyed off `(document, section, provider, model)` returns artifact rows; needs to query entity rows post-refactor.
- **Pydantic field naming on existing `Document` references**: `document_id` is already used everywhere; consistency check across new models.
- **OpenAPI client surface growth**: 6 new entity types × CRUD = ~24 new endpoints in the Swift client. Build time goes up; manageable.

## 8. Tests we lock

- DuckDB round-trip per entity type (save then query, all fields preserved).
- Extractor produces N rows for N items.
- Read API filters correctly by document_id.
- Inspector view renders empty state, single item, and many-items.
- Migration: legacy artifact → new entity rows, idempotent.

## 9. Decisions needed before locking

Before I generate the line-by-line implementation plan, mark **DECIDE** on:

1. §3.1 — schema topology: **A** (per-type tables), B (polymorphic), or other?
2. §3.2 — FK model: A (entity→doc only), B (via artifact), or **C** (both, denormalized)?
3. §3.3 — markdown coexistence: A (drop), B (both), or **C** (free-form only)?
4. §3.4 — migration: A (lazy), **B** (explicit one-shot), C (legacy stays), D (forced)?
5. §3.5 — dedup: A (save-time), B (read-time), or **C** (punt to 0.0.3+)?
6. §3.6 — extensibility: **A** (hard-coded types), B (declarable)?

Bold = my recommendation. Reply with edits or "lock A/C/C/B/C/A" and I run `writing-plans` to generate the bite-sized TDD plan from this design.
