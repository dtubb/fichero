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
- `kg.tables.filter.text` [OK] — a per-table filter field narrows rows by text.
  Built: `EntitiesLibraryContent.swift:~136` (`TextField("Filter entities", ...)` feeding
  `entityMatches`), `ClaimsLibraryContent.swift:~163` (`TextField("Filter claims", ...)`
  feeding `claimMatches`).
- `kg.tables.filter.entity-type` [OK] — an entity-**type** picker filters the entity
  table. Built: `EntitiesLibraryContent.swift:~127-146` (`availableTypes` + type `Menu`).
- `kg.tables.filter.claim-type` [PARTIAL] (#4768) — a claim **type** picker filters the claim
  table (built: `ClaimsLibraryContent.swift:~151-176`, `availableTypes`/type `Menu`
  filtering `claimType`), but there is no curation-state picker — the spec line
  originally promised "type / curation-state" and only type shipped.
- `kg.tables.filter.combines-with-search` [OK] — the per-table filter AND the shared ⌘F
  query both apply (intersection); neither clobbers the other. Built: `entityMatches`
  (`EntitiesLibraryContent.swift:~109-123`) / `claimMatches`
  (`ClaimsLibraryContent.swift:~136-151`) both check `search` and `filterText`.
- `kg.tables.filter.empty-state` [OK] — a filter that matches nothing shows "No matches",
  never a blank table or a spinner. Built: `ClaimsLibraryContent.swift:~192-203`
  (`emptyMessage`); `EntitiesLibraryContent` has the parallel empty state.
- `kg.tables.filter.pushdown` (later) — for large sets, push the filter to the list
  endpoint (`q` / `entity_type` / `claim_type` already exist) instead of client-side only.

### B. Entity CRUD (#4624)
- `kg.tables.entity.create` [OK] — a "New Entity" affordance creates an entity (canonical
  name + type), selects the new row, and enters rename. Built:
  `EntitiesLibraryContent.swift:~77` (`showingCreateSheet`/`handleCreatedEntity`), id
  `kg.entity.new`.
- `kg.tables.entity.rename-inline` [OK] — the canonical name is editable from the table.
  Built: `EntitiesTableView.swift:~118-125` (inline `TextField` + `commitRename`).
- `kg.tables.entity.retype` [OK] — entity type is editable (keep).
- `kg.tables.entity.delete` [OK] — delete removes the entity and its claim links, undoable.
- `kg.tables.entity.curate` [OK] — bless / reject / merge stay.

### C. Claim CRUD (#4624)
- `kg.tables.claim.create` [OK] — a "New Claim" affordance hand-authors a claim, wiring
  POST /api/claims. Built: `NewClaimSheet.swift` (view), `EntityService+
  ClaimEntityCRUD.swift:~117` (`createClaim`), wired from `ClaimsLibraryContent.swift`
  (`showingCreateSheet`), id `kg.claim.new`.
- `kg.tables.claim.create.source-optional-flagged` — a hand-authored claim MAY have no
  source (a working hypothesis / synthesis), but it is clearly marked "no source" and
  treated as lower-provenance; it is never silently indistinguishable from a sourced claim.
- `kg.tables.claim.edit` [OK] — subject/verb/object + fields editable **from the
  claim table** is built: `ClaimsTableView.swift:~168-172` wires an `onEdit` menu item
  (`kg.claim.menu.edit`) that opens the existing `EditClaimSheet` (S·V·O + type +
  epistemic status, PATCH `/api/claims/{id}`), reused rather than re-parsed. Shipped
  in `a166ad3ee` (2026-09-08, "feat(kg-tables): edit a claim from the claims table
  (#4624)"). The row-level `claimMenu` doc-comment's "edit / curate arrive in later
  kg-tables waves" is stale for edit (curate is the real remaining gap — see
  `kg.tables.claim.curate` below). Pinned:
  `fichero/Tests/Unit/general/Views/Library/ClaimsTableCreateTests.swift::testClaimsTableOffersEditReusingTheExistingSVOEditor`.
- `kg.tables.claim.delete` [PARTIAL] (#4643) — delete **from the table** is built:
  `ClaimsTableView.swift:~166-183` (`onDelete` menu item, `kg.claim.menu.delete`) →
  `ClaimsLibraryContent.swift:~254-268` (`deleteClaims`, one audited delete per id, reloads
  on failure). Left [PARTIAL] pending `kg.scale.batch-delete` (sequential per-id calls, no
  batch endpoint yet — see Scale section below).
- `kg.tables.claim.curate` [PARTIAL] (#4691) — bless / reject / merge from the table.
  Verified against code (2026-09-18): `ClaimsTableView.swift:158-184` (`claimMenu`) offers
  only Edit and Delete — no bless/reject/merge menu item. Curation is reachable only via
  batch MCP tools, not the table row menu (`#4691`, table row "claim curate … from table
  ✗ `ClaimsTableView.swift:158` 'Delete only, for now'").

### D. Cross-cutting (both tables)
- `kg.tables.crud.cross-surface` (creative-director ruling, 2026-09-08) — every KG CRUD
  capability (claim delete, entity create, claim create, edits) must exist across the WHOLE
  spine: **backend → UX (table) → AI (MCP) + CLI → tests → export**, not only the SwiftUI
  table. A capability that works in the table but not via MCP/CLI is NOT done. Each CRUD
  behavior below is delivered in all surfaces or tracked as an explicit gap.
- `kg.tables.crud.audited` — every create/edit/delete is ONE typed, audited backend action,
  reversible via the mutation log (one-audited-action-layer).
- `kg.tables.crud.in-place` — a create/edit/delete updates that one row in place; the table
  is not wholesale re-rendered (stores update one item, not the list).
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
- `kg.tables.provenance.careful-versions` — versions are kept carefully so a prior value is
  recoverable, not just overwritten. (Backend has a `MutationLog` for undo; surface it.)
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
  ⌘-click; keep it.
- `kg.view.keyboard-delete` [MISSING] — ⌘⌫ deletes the selection; ⌘A selects all — same
  selection grammar as every other library mode (`check_selection_grammar`, #4436).
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
