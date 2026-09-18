# KG Tables — Design Spec (#4624 CRUD · #4625 filter)

> Milestone: kg-tables

> Design-led (Testing Constitution). The Fichero creative director owns this intent;
> tests enforce it; code makes them pass. One line per behavior, each cited by its
> pinning test. Status: APPROVED — creative director ratified; first-wave CRUD + filters shipped.
> Tags: [OK] today · [MISSING] not built · [PARTIAL] exists elsewhere, not in the table.

## Intent (the design)

The entity table and the claim table are where a researcher **browses, filters, and
curates** the knowledge graph — and **hand-authors** it, not only what AI extracted. Full
CRUD lives in the tables themselves, every action is one audited, reversible backend
action, and a change updates the one row in place (never a whole-table re-render). A
filter narrows what's shown without touching what exists.

Surfaces: `EntitiesLibraryContent` / `EntitiesTableView`, `ClaimsLibraryContent` /
`ClaimsTableView`, `EntityStore`, `ClaimStore`, `EntityService`, backend
`api/routes/entity/*` + `api/routes/claim/*` (CRUD already complete server-side).

## Behaviors

### A. Filter (#4625)
- `kg.tables.filter.text` [OK] (Pinned: `ClaimsFilterTests`, `EntitiesFilterTests`.) — a per-table filter field narrows rows by text.
  Built: `EntitiesLibraryContent.swift:~136` (`TextField("Filter entities", ...)` feeding
  `entityMatches`), `ClaimsLibraryContent.swift:~163` (`TextField("Filter claims", ...)`
  feeding `claimMatches`).
- `kg.tables.filter.entity-type` [OK] — an entity-**type** picker filters the entity
  table. Built: `EntitiesLibraryContent.swift:~127-146` (`availableTypes` + type `Menu`).
  Pinned: `EntitiesFilterTests`.
- `kg.tables.filter.claim-type` [PARTIAL] (#4768) — a claim **type** picker filters the claim
  table (built: `ClaimsLibraryContent.swift:~151-176`, `availableTypes`/type `Menu`
  filtering `claimType`), but there is no curation-state picker — the spec line
  originally promised "type / curation-state" and only type shipped.
- `kg.tables.filter.combines-with-search` [OK] (Pinned: `ClaimsFilterTests`,
  `EntitiesFilterTests`.) — the per-table filter AND the shared ⌘F
  query both apply (intersection); neither clobbers the other. Built: `entityMatches`
  (`EntitiesLibraryContent.swift:~109-123`) / `claimMatches`
  (`ClaimsLibraryContent.swift:~136-151`) both check `search` and `filterText`.
- `kg.tables.filter.empty-state` [OK] (Pinned: `ClaimsFilterTests`, `EntitiesFilterTests`.) — a filter that matches nothing shows "No matches",
  never a blank table or a spinner. Built: `ClaimsLibraryContent.swift:~192-203`
  (`emptyMessage`); `EntitiesLibraryContent` has the parallel empty state.
- `kg.tables.filter.pushdown` (later) — for large sets, push the filter to the list
  endpoint (`q` / `entity_type` / `claim_type` already exist) instead of client-side only.

### B. Entity CRUD (#4624)
- `kg.tables.entity.create` [OK] (Pinned: `EntitiesTableCreateTests`.) — a "New Entity" affordance creates an entity (canonical
  name + type), selects the new row, and enters rename. Built:
  `EntitiesLibraryContent.swift:~77` (`showingCreateSheet`/`handleCreatedEntity`), id
  `kg.entity.new`.
- `kg.tables.entity.rename-inline` [OK] — the canonical name is editable from the table.
  Built: `EntitiesTableView.swift:~118-125` (inline `TextField` + `commitRename`). Pinned:
  `EntitiesTableCreateTests`.
- `kg.tables.entity.retype` [OK] — entity type is editable (keep). Pinned:
  `KGInspectorCRUDUITests`.
- `kg.tables.entity.delete` [OK] — delete removes the entity and its claim links, undoable.
  Pinned: `KGInspectorCRUDUITests`.
- `kg.tables.entity.curate` [PARTIAL] (implemented, unpinned; #4801, → #1765, → #1786) — bless
  / reject / merge stay. → #1786 asked for entity rename + "Add entity" specifically — both
  are now [OK] (`kg.tables.entity.rename-inline`/`.create` above); kept open as a verify-close
  candidate rather than closed by this pass, since curate (bless/reject/merge) itself is still
  only [PARTIAL]. → #1765 is the broader origin ask (approve/reject/edit entities AND claims,
  `curation_state` end-to-end) — its "also in WebKit" clause is moot now the KG browser has
  retired (#4828); what remains open is the inspector-only half this behavior tracks.
  Cross-ref: `kg-readable-representation.md`'s `kg.read.edit-unit-is-the-claim` covers a
  DIFFERENT surface reaching the same `claim.patch` action — editing FROM a rendered sentence
  rather than from this table — the two should stay in sync as both land.

### Unreachable since the KG browser retired (#4828) — awaiting a re-mount-or-retire decision

Six working views lost their only entry point when the KG sidebar mode and `OntologyBrowser`
retired; each is KEPT (not dead code — a feature whose entry point retired is not the same as
an unused renderer), pending a decision on where it re-mounts. None of these are built or
tested against a NEW entry point yet — each stays [GAP] until re-mounted.

- `kg.entity.menu.merge` — **[GAP]** (#4828, → #1675) `EntityMergeSheet` merges duplicate
  entities. Cross-references `kg.tables.entity.curate` above (#4801) rather than duplicating
  it — the merge CAPABILITY is the same one that behavior already tracks; this entry is about
  the sheet's own re-mount location specifically. → #1675 asks for more than the sheet: a
  reversible AUDIT TRAIL for merge/split decisions (source ids, who/why, undo/re-split), not
  built yet on either side.
- `kg.entity.menu.split` — **[GAP]** (#4828, → #1675) `EntitySplitSheet` splits a conflated
  entity. Not named in any of the three KG specs before this pass. See #1675's audit-trail ask
  above. → #1688 additionally asks for the SAME merge/unmerge/alias/edit surface reachable via
  the CLI, not just the UI sheets — the CLI half is unbuilt on either side.
- `kg.claim.contradiction-triage` — **[GAP]** (#4828, → #1677) `ContradictionTriageSheet`
  triages contradicting claims. Not named before this pass. → #1677 is the broader ask: a
  review UI covering EVERY workflow stage (transcript → imported entities → merge → KG →
  ontology), of which contradiction triage is one stage.
- `kg.claim.review-queue` — **[GAP]** (#4828, → #372) `ClaimReviewQueueSheet`, a review queue
  for unreviewed claims. Not named before this pass. → #372 is the original ask (queue with
  `unreviewed → shortlisted → curated/rejected` transitions, filter by person/topic, batch or
  single-item) — `ClaimReviewQueueSheet` exists but is unreachable since the browser retired,
  same as this behavior's own [GAP] tag says.
- `kg.entity.kind-chart` — **[GAP]** (#4828) `EntityKindChartView`, entity counts by kind. Not
  named before this pass.
- `kg.claim.speaker-comparison` — **[GAP]** (#4828) `SpeakerComparisonView`, claims compared
  per speaker. Not named before this pass.

Enrichment's two unreachable views (`WikidataEnrichmentSheet`, `HeuristicReviewSheet`) are
`kg/kg-enrichment.md`'s (→ #4759, already named there) — not duplicated here.

### C. Claim CRUD (#4624)
- `kg.tables.claim.create` [OK] (Pinned: `ClaimsTableCreateTests`.) — a "New Claim" affordance hand-authors a claim, wiring
  POST /api/claims. Built: `NewClaimSheet.swift` (view), `EntityService+
  ClaimEntityCRUD.swift:~117` (`createClaim`), wired from `ClaimsLibraryContent.swift`
  (`showingCreateSheet`), id `kg.claim.new`.
- `kg.tables.claim.create.source-optional-flagged` — a hand-authored claim MAY have no
  source (a working hypothesis / synthesis), but it is clearly marked "no source" and
  treated as lower-provenance; it is never silently indistinguishable from a sourced claim.
- `kg.tables.claim.edit` [OK] (Pinned: `ClaimsTableCreateTests`.) — subject/verb/object + fields editable **from the
  claim table** is built: `ClaimsTableView.swift:~168-172` wires an `onEdit` menu item
  (`kg.claim.menu.edit`) that opens the existing `EditClaimSheet` (S·V·O + type +
  epistemic status, PATCH `/api/claims/{id}`), reused rather than re-parsed. Shipped
  in `a166ad3ee` (2026-09-08, "feat(kg-tables): edit a claim from the claims table
  (#4624)"). The row-level `claimMenu` doc-comment's "edit / curate arrive in later
  kg-tables waves" is stale for edit (curate is the real remaining gap — see
  `kg.tables.claim.curate` below). Pinned:
  `fichero/Tests/Unit/general/Views/Library/ClaimsTableCreateTests.swift::testClaimsTableOffersEditReusingTheExistingSVOEditor`.
- `kg.tables.claim.delete` [PARTIAL] (#4643, → #1787) — delete **from the table** is built:
  `ClaimsTableView.swift:~166-183` (`onDelete` menu item, `kg.claim.menu.delete`) →
  `ClaimsLibraryContent.swift:~254-268` (`deleteClaims`, one audited delete per id, reloads
  on failure). Left [PARTIAL] pending `kg.scale.batch-delete` (sequential per-id calls, no
  batch endpoint yet — see Scale section below). → #1787 asks that claim delete be wired
  EVERYWHERE approve/reject/suppress live, single + multi, with confirm — the table's own
  delete is built; approve/reject/suppress-with-confirm is `kg.tables.claim.curate` below,
  still [PARTIAL].
- `kg.tables.claim.curate` [PARTIAL] (#4691, → #1751) — bless / reject / merge from the table.
  Verified against code (2026-09-18): `ClaimsTableView.swift:158-184` (`claimMenu`) offers
  only Edit and Delete — no bless/reject/merge menu item. Curation is reachable only via
  batch MCP tools, not the table row menu (`#4691`, table row "claim curate … from table
  ✗ `ClaimsTableView.swift:158` 'Delete only, for now'"). → #1751 is a broader EPIC (unified
  multi-select curate/enable/disable/group/delete/merge across files, folders, entities AND
  claims) — kept open here for its entities/claims slice specifically; the files/folders half
  is `sidebar-crud.md`'s territory, not this spec's.

### C2. Deeper CRUD/UX asks not yet behaviors
- `kg.tables.entity.descendant-aggregation-provenance` — **[GAP]** (#2020) when a folder/PDF
  in the sidebar is selected, the entity panel aggregates the entities of the selection AND
  all its children UNDIFFERENTIATED — no way to tell which document an entity came from.
  Wanted: convert the flat List to a Table with a clickable "Found in" column (entity-grouped,
  default includes-children), so descendant aggregation stays but gains provenance.
- `kg.tables.schema-complete-field-display` — **[GAP]** (#1768) the inspector surfaces only a
  few fields of the KG data model's rich schema; wanted: show the COMPLETE field set of a
  claim/entity/artifact so a user can see everything that's actually available, not a curated
  subset chosen ahead of time.
- `kg.tables.entity.row-density-and-source-count` — **[GAP]** (#1788) entity rows are
  full-width; lozenges should be text-width and flow/wrap into rows for information density,
  and the source count shown per row should be accurate (some entities have several sources
  and the count under-reports).
- `kg.tables.crud.inline-not-modal` — **[GAP]** (#1888) claim/entity editing today happens in
  modal sheets (`EditClaimSheet`, `OntologyBrowser`'s create sheet, `EntityMergeSheet`/
  `EntitySplitSheet`) — the ask is inline editing / navigation-with-Back instead of a sheet
  stack, matching the Finder-like direct-manipulation principle the rest of the tables follow.
- `kg.tables.entity-resolution-registry` — **[GAP]** (#1761) a persisted "entity checker":
  human merge/alias/reclassify/split fixes on existing entities should CONSTRAIN future
  imports — re-importing the same folder should respect corrections already made rather than
  re-creating the entities a human already fixed. Ties to the standing curation-persists-and-
  constrains-imports ruling; this behavior is the KG-entity half specifically (the importer's
  own NLP-draft half is `importer.md`'s `importer.nlp-never-overwrites-curated-rows`).

### D. Cross-cutting (both tables)
- `kg.tables.crud.cross-surface` (creative-director ruling, 2026-09-08) — every KG CRUD
  capability (claim delete, entity create, claim create, edits) must exist across the WHOLE
  spine: **backend → UX (table) → AI (MCP) + CLI → tests → export**, not only the SwiftUI
  table. A capability that works in the table but not via MCP/CLI is NOT done. Each CRUD
  behavior below is delivered in all surfaces or tracked as an explicit gap.
- `kg.tables.crud.audited` — every create/edit/delete is ONE typed, audited backend action,
  reversible via the mutation log (one-audited-action-layer).
- `kg.tables.crud.in-place` — **[PARTIAL]** (#4389) a create/edit/delete updates that one row
  in place; the table is not wholesale re-rendered (stores update one item, not the list).
  Basic create/edit/delete honor this (sections B/C above), but **merging entities re-fetches
  the whole inspector list** instead of updating the merged rows in place — a direct
  counter-example, same class of regression `harness/observable-data-layer.md`'s
  `observable.store-mutator-updates-in-place` tracks generally, filed here specifically
  because it's the KG entity-merge path.
- `kg.tables.crud.validation` — a create/edit is validated at the boundary (non-empty
  canonical name; a claim needs at least a subject or text); an invalid input is refused
  with an inline reason, not silently dropped.

### E. Provenance + versions (creative-director priority — likely its own cross-cutting spec)
- `kg.tables.provenance.author-mark` — a claim/entity shows who AUTHORED it: hand-authored
  (human) vs AI-extracted, at a glance. (Backend records `created_by`.)
- `kg.tables.provenance.modification-chain` — and who MODIFIED it, in order, each step
  labeled by the actor: an AI extractor (e.g. "apple-vision", "sonnet-5.1") or a human.
  "Apple Vision created it → Sonnet 5.1 changed it → hand-edited by you" is visible.
- `kg.tables.provenance.hand-edit-recorded` — a manual edit is recorded AS a human edit in
  the chain (never attributed to the model whose value it replaced).
- `kg.tables.provenance.careful-versions` — **[GAP]** (#4644) versions are kept carefully so a
  prior value is recoverable, not just overwritten. (Backend has a `MutationLog` for undo;
  surface it.) #4644 is the broader ask this section's provenance/version display answers:
  drag&drop reorganization, a full context menu (merge/combine/comment), select→export
  JSON-LD, and surfacing claim provenance/geo/time alongside versioning. The export-JSON-LD
  half is `kg-enrichment.md`'s `kg.jsonld.export` (already [OK]) wired to a table selection,
  not a new export mechanism; drag&drop/context-menu/comment are UI affordances not yet built
  on top of the CRUD this spec already tracks.
- NOTE: this is the foundational **provenance + version model** now specced separately at
  **#4636** (full restorable history · reasoning capture · extensible actor roles
  extractor/editor/reviewer/end-user + representation types) — sibling of the anchor model
  #4635. The KG tables are its FIRST surface, but the display here rides that model. So
  Section E lands AFTER #4636's model exists; the tables' first waves (filters + CRUD
  below) do NOT block on it and ship first.

## Scale, bulk operations & first-class library view (creative-director review, 2026-09-09)

The tables must behave like a **first-class Mac library view** at archive scale (1k–100k
entities/claims), not a small demo table. What's missing:

### Bulk operations at scale
- `kg.scale.batch-delete` [MISSING backend] (#4643) — deleting N rows is N sequential per-id DELETEs
  today (1000 rows = 1000 round-trips) AND aborts mid-loop on one failure, leaving the UX
  showing already-deleted rows (drift). Batch endpoints EXIST for transition / upsert /
  curation (`/api/claims/batch/transition`, `/api/entities/batch`, `/api/kg/claims/batch-
  curation`) but **not delete** — add `POST /api/claims/batch-delete` + `/api/entities/
  batch-delete` (one audited, atomic-where-possible action) so 1k–10k is one call.
- `kg.scale.bulk-correctness` — a bulk op prunes exactly the rows that SUCCEEDED (partial
  failure never drifts the UX); interim client fix = bounded-concurrent deletes collecting
  successes (reuse the `BatchService` maxConcurrent task-group pattern) until the endpoint lands.
- `kg.scale.normalize-names` [MISSING] (#4643) — a bulk "normalize / canonicalize names" op over a
  selection (or the whole library) via a provider/AI: fold "Matheo del Mazo" / "Mateo del
  Mazo" to a canonical form + merge. A batch curation/enrichment action, not per-row.
- `kg.scale.progress-cancel` — a long bulk op shows progress and is cancellable; bounded so
  it never pegs the machine (Article 4 resource-safety).

### First-class library view affordances
- `kg.view.contiguous-selection` [OK] — Set-based selection gives shift-click range +
  ⌘-click; keep it. Pinned: `SelectionGrammarTests`.
- `kg.view.full-row-click-target` — **[GAP]** (#4607) the entities list's click target should
  be the FULL row, not just the label text, so the existing selection grammar
  (`kg.view.contiguous-selection` above) is easy to invoke for bulk curation — today a
  narrower click target makes multi-select fiddly even though the underlying grammar works.
- `kg.view.keyboard-delete` [MISSING] — ⌘⌫ deletes the selection; ⌘A selects all — same
  selection grammar as every other library mode, enforced by `check_selection_grammar.py`.
  Was mis-cited to the four-selection-implementations root-cause issue (long since closed —
  that unified only the CLICK grammar, not keyboard delete/select-all); the actual remainder
  is filed as #4794.
- `kg.view.type-icons` [MISSING] (#4643) — rows use the per-type icons that ALREADY exist
  (`KnowledgeGraphSupport`: person/place/org/event/concept/date), not one flat glyph.
- `kg.view.pagination` [MISSING at 10k] (#4643) — the table loads up to 25 000 client-side; at
  10k+ push filter/scope to the list endpoint (`filter.pushdown`) and page, so memory and
  first-paint stay bounded.

### Test coverage for scale — Swift + UX + backend + LOAD (all required)
| Behavior | Backend (pytest) | Swift (unit) | UX (XCUITest) | Load/background (#4634) |
|---|---|---|---|---|
| batch-delete | endpoint deletes N atomically; audited; partial reported | bounded/bulk delete prunes only successes | select many → delete → rows gone | delete 1k/10k bounded, no peg, timed |
| normalize-names | batch op merges canonically | pure canonicalize rule | select → normalize → merged | 10k under bounded concurrency |
| keyboard-delete | — | command maps to delete action | ⌘⌫ removes selection | — |
| type-icons | — | pure icon-for-type mapping | rows show right icons | — |

## Accessibility identifiers (for the click-around leg — TEST-TEMPLATE)

Stable ids on the KG tables so an XCUITest can find + act on them:
- rows: `kg.entity.row.<id>` · `kg.claim.row.<id>`
- entity menu: `kg.entity.menu.{rename,edit,bless,reject,merge,delete}`
- claim menu: `kg.claim.menu.{edit,delete}`
- create: `kg.entity.new` · `kg.claim.new`

(More as interaction verbs land — comment/export/combine, #4644.)

## First wave to pin (proposed)
1. Filters: `filter.text` + `filter.entity-type` / `filter.claim-type` +
   `filter.combines-with-search` + `filter.empty-state` (#4625) — cleanest, no backend work.
2. Claim `delete` + entity `create` in the table (wire existing store/service).
3. Claim `create` (new POST /api/claims wiring: service + store + a NewClaimSheet).
4. Inline entity rename + claim edit-from-table.

## Manual-create is intended (creative-director ruling, 2026-09-08)
A researcher can hand-author a claim/entity, not just curate AI output — a real archival
workflow. So `claim.create` (POST /api/claims) and `entity.create` in the table are in
scope, with `crud.validation` guarding the input.

## Findings (from the CRUD-matrix scout, this session) — HISTORICAL, superseded 2026-09-17
Backend CRUD is COMPLETE (entities + claims: create/read/update/delete + curation). The
gaps are all UI wiring: claim **create** missing (no service/store/view); claim
edit/delete exist but are wired only into the Ontology cards, not the claim TABLE; the
entity table lacks create + inline rename. Filters are client-side on the shared ⌘F query
only — no dedicated field. (Details on #4624 / #4625.)

This is now FALSE — claim create, entity create, entity inline rename, and per-table
filter fields (text + entity-type/claim-type) all shipped since this scout ran; see the
retagged behaviors in sections A/B/C above for current evidence. Kept for history, not as
current status.
