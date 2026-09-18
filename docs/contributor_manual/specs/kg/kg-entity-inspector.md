# KG Entity Inspector — Design Spec

> Milestone: kg-entity-inspector

> Design-led spec (Testing Constitution, #4623, milestone Knowledge Graph). The
> creative director owns this intent; tests enforce it; code makes the tests pass.
> One line per behavior; each maps to a pinning test cited by name in the test's
> docstring.
> Status: APPROVED (option a). F2+F3+F5 landed (eb5b868c6, 7ee417fbc, 1eb9b9557).
> Spec-audit 2026-09-13 retagged stale [BROKEN] lines to [OK] + added test citations.
> TEST GAPS now pinned (2026-09-16) in
> `Tests/Unit/general/Views/Inspector/EntityInspectorPinningTests.swift`:
> F3 `statements.loads-via-store` (`entityLoadRoutesThroughStoreScope` +
> `digestLoadsViaClaimStore`) + `statements.resyncs-on-change`
> (`digestObservesChangeToken` + `storeExposesChangeToken`);
> `select.routes-to-entities-tab` (`focusRoutesToEntitiesTab`);
> `select.never-another-entity` + `rekey.on-focus-change`
> (`entityArmRekeysAndClearsOnFocusChange` + `digestStatementsRekeyOnEntity`);
> `xsurface.same-line` (`sameLineAcrossSurfaces` + `surfacesRouteThroughOneComposer`).
> Field-based builder migration is a follow-up.
>
> Tags: **[OK]** behaves this way today · **[BROKEN]** regression, code contradicts
> the line · **[GAP]** intended behavior never built. Untagged = design intent whose
> current state is not yet pinned either way.

## Intent (the design)

An entity is a *name*; its statements are what the library knows about it. Selecting
an entity — in the Entities collection table, the ontology list, the force graph, or
a document's Entities tab — shows THAT entity in the inspector: its statements (the
subject–verb–object claims where it is subject or object), each with where it was
said, and each statement is a door back to its source with the passage lit. The
inspector never shows "No selection" while an entity is focused, and it never shows
a different entity's statements than the one focused. A statement reads and behaves
the same wherever it renders — the inspector, the ontology card, the digest — one
line composer, one anchor builder, one source cursor.

Surfaces: `DocumentInspector` (+`Sections`), `DocumentInspectorEntitiesTab`
(`entityDetailPane` → `EntityDigestContent`), `KnowledgeGraphInspectorSection`,
`KGFocusState`, `ClaimStore`, `ClaimSourceRequest` → `ClaimSourceNavigationState` →
`ContentView.handleOpenClaimSource`.

## Behaviors (each → one pinning test)

### A. Selection → focus → inspector

- `kg.entity.select.focuses` — [OK] selecting an entity anywhere (entities table,
  ontology list, force graph, Entities tab row) sets `KGFocusState.focusedEntityId`
  to that entity and clears any focused claim. Pinned: `KGFocusStateTests`
  (`Tests/Unit/general/Models/KGFocusStateTests.swift`).
- `kg.entity.select.inspector-shows-entity` — **[OK]** (F2 landed, eb5b868c6) while an
  entity is focused the inspector shows that entity, even when no document is selected
  (the Entities collection and the Knowledge Graph mode select an entity, not a file).
  Was: fell to `emptyState` ("No selection") because its `document` was nil. Pinned:
  `DocumentInspectorArmTests`
  (`Tests/Unit/general/Views/Inspector/DocumentInspectorArmTests.swift` — the extracted
  pure `DocumentInspector.inspectorArm(...)` decision).
- `kg.entity.select.routes-to-entities-tab` — [OK] when a document IS shown, focusing
  an entity switches the inspector to the Entities tab and selects that entity's row
  in the list. (`DocumentInspector.swift:98-102`, `syncSelectionToFocusedEntity`)
  Pinned: `EntityInspectorPinningTests` (`focusRoutesToEntitiesTab`).
- `kg.entity.select.never-another-entity` — the entity pane shows the focused entity,
  or the empty state — never the previous entity's statements under a new header
  (the #965 class). Pinned by re-keying (section D): `EntityInspectorPinningTests`
  (`entityArmRekeysAndClearsOnFocusChange`).

### B. Statements list

- `kg.entity.statements.loads-via-store` — **[OK]** (F3 code landed,
  7ee417fbc; pinned 2026-09-16) the entity's claims are fetched through
  `ClaimStore.loadClaims(forEntity:)` (the observable data layer), not a direct
  `entityService.listClaims` call from the view. Pinned: `EntityInspectorPinningTests`
  (`entityLoadRoutesThroughStoreScope` — the store owns the entity scope;
  `digestLoadsViaClaimStore` — the digest prefers the store, keeping the direct fetch
  only as the no-store fallback).
- `kg.entity.statements.subject-or-object` — [PARTIAL] (implemented, unpinned;
  #4802) the list contains every claim where the entity is subject OR object
  (`GET /api/claims?entity_id=…`), not only claims where it is the subject.
- `kg.entity.statements.row-shows-svo` — [OK] each row renders the typed triple via
  `ClaimLine.text(...)` with the focused entity as `groupSubject`, so its own name is
  omitted when redundant and kept when the claim is about someone else; a claim with
  no triple falls back to its text. Pinned: `ClaimLineTests`.
- `kg.entity.statements.row-shows-source-label` — each row names where it was said:
  the source document's display name and page label when known; "Source <id>…" only
  when the document cannot be resolved; never an empty badge.
- `kg.entity.statements.sorted-newest-first` — [PARTIAL] (implemented, unpinned;
  #4802) rows are ordered newest-first (`createdAt` descending), matching the
  ontology detail panel.
- `kg.entity.statements.resyncs-on-change` — **[OK]** (F3 code landed,
  7ee417fbc; pinned 2026-09-16) the list refreshes when any claim mutates anywhere
  (`ClaimStore.changeToken`), so an edit, merge, delete or curation change on another
  surface is visible here without reselecting. Pinned: `EntityInspectorPinningTests`
  (`digestObservesChangeToken` — the digest re-loads on a token bump;
  `storeExposesChangeToken`); the token movement itself is pinned by
  `ClaimChangeDeliveryTests`.
- `kg.entity.statements.loading-state` — while claims load, a progress indicator
  shows and no stale list from a previous entity is visible.

### C. Statement → source (click-through)

- `kg.entity.source.row-click-navigates` — [OK] selecting a statement row posts a
  `ClaimSourceNavigationRequest` on the window's `ClaimSourceNavigationState`; the
  shell resolves the page child to its parent, selects it, and scrolls the reader to
  the page (`handleOpenClaimSource`). Pinned: `ClaimSourceRequestTests`.
- `kg.entity.source.highlights-span` — [OK] a claim with a recorded non-empty
  character span (`sourceCharStart < sourceCharEnd`) highlights that passage. Pinned:
  `ClaimSourceRequestTests`.
- `kg.entity.source.highlights-region` — [OK] a claim with a recorded region
  (`sourceAnchor.rect`, four values) and no span highlights that bbox on the page
  image. Pinned: `ClaimSourceRequestTests`.
- `kg.entity.source.page-only-no-highlight` — [OK] a claim with a document but no
  span and no region opens the page and draws NO highlight (never approximate a
  location — `ClaimSourceRequest.Precision.pageOnly`). Pinned: `ClaimSourceRequestTests`.
- `kg.entity.source.no-document-no-navigation` — [OK] a claim with no source
  document produces no request; the row is inert rather than navigating to nothing.
  Pinned: `ClaimSourceRequestTests`.
- `kg.entity.source.one-anchor-builder` — **[OK]** (F5 landed, 1eb9b9557; field-based
  builder migration is a follow-up) every entity-statement surface builds its request
  through the precision-aware builder, so no two surfaces disagree about whether a
  highlight is drawn for the same claim. Pinned: `ClaimSourceRequestTests`
  (`sameAnchorAcrossBuilders` — calls both builders on fixture claims and diffs
  outputs — the cross-surface invariant).
- `kg.entity.source.open-entity-is-search` — [PARTIAL] (implemented, unpinned;
  #4802) OPENING the entity itself (double-click / "Open") is the scoped mention
  search, not a jump to one arbitrary claim's page (ruled 2026-09-05, option A). An
  entity has no page; its statements do. This is why no `EntitySourceRequest` type
  is proposed — see Findings F6.

### D. Empty state and re-keying

- `kg.entity.empty.no-claims` — **[OK]** an entity with zero claims shows "No statements
  about <name> yet" (not a blank pane, not a spinner, not the previous entity's
  rows). Pinned: `EntityDigestStatementsStateTests`
  (`Tests/Unit/general/Views/Inspector/EntityDigestStatementsStateTests.swift` — pure
  `EntityDigestContent.statementsState(...)`).
- `kg.entity.empty.load-error` — a failed load shows the error inline with a way to
  retry; it does not fall back to a stale list.
- `kg.entity.rekey.on-focus-change` — the statements view is keyed on
  `focusedEntityId` (`.task(id:)`), so changing focus re-fetches and the list
  belongs to the new entity; the old list is dropped, not appended. Pinned:
  `EntityInspectorPinningTests.entityArmRekeysAndClearsOnFocusChange` +
  `.digestStatementsRekeyOnEntity`.
- `kg.entity.rekey.clear-focus-clears-pane` — when focus clears (`KGFocusState.clear`,
  selection emptied) the entity pane goes away and the inspector returns to its
  document (or the ordinary empty state).

### E. Cross-surface invariant

- `kg.entity.xsurface.same-line` — the same claim renders the same statement line in
  the inspector entity pane, the ontology `ClaimSummaryCard`, and the entity digest:
  one composer (`ClaimSummaryCard.svoTriple` + `ClaimLine.text`), tested once as an
  invariant over a fixture claim set, not per surface. Pinned:
  `EntityInspectorPinningTests.sameLineAcrossSurfaces` (composer invariant) +
  `.surfacesRouteThroughOneComposer` (no surface hand-rolls its own).
- `kg.entity.xsurface.same-anchor` — **[OK]** the same claim yields an identical
  `ClaimSourceNavigationRequest` (document, page, span/bbox, precision) from every
  surface — the one-builder line above, asserted as an invariant. Pinned:
  `ClaimSourceRequestTests` (`sameAnchorAcrossBuilders`).

### F. Unreachable since the KG browser retired (#4828) — awaiting a re-mount-or-retire decision

`EntityDetailView` lost its only entry point when the KG sidebar mode retired; a section-by-
section audit found most of it superseded by this inspector already (history, the claims
block, kind hide/show, mentions/biography), but five capabilities exist NOWHERE else in the
app and are KEPT (not dead code), pending a decision on where each re-mounts. All stay [GAP]
until re-mounted and tested against the new location.

- `kg.entity.notes` — **[GAP]** (→ #4828) notes attached to an entity — add / list / delete
  (`EntityDetailView+Notes.swift`'s `EntityNotesSection`).
- `kg.entity.alias-editing` — **[GAP]** (→ #4828) list/edit an entity's aliases
  (`EntityDetailView+Sections.swift`'s `aliasesSection`).
- `kg.entity.raw-metadata-editing` — **[GAP]** (→ #4828) view AND edit an entity's raw metadata
  as JSON (`EntityDetailView+Sections.swift`'s `metadataSection`,
  `EntityDetailView+Metadata.swift`'s `saveMetadataJSON`).
- `kg.entity.authority-link-create` — **[GAP]** (→ #4828) link an entity to an external
  authority record. This inspector can DISPLAY a past authority-link audit event already, but
  nothing anywhere can CREATE one any more — `EntityDetailView+Metadata.swift`'s
  `authorityLinkButton`/`EntityAuthorityLinkSheet` is the only place that ever could. Coupled
  to Wikidata enrichment (`kg/kg-enrichment.md`, → #4759) — the enrichment sheet's own
  comment says it builds on the authority link, so the two should re-mount together, not
  independently.
- `kg.entity.claims-grouped-by-source` — **[GAP]** (→ #4828) group an entity's claims by their
  source document (`EntitySourceGroupsView.swift`, the `sourceGroupsMode` toggle in
  `EntityDetailView+Claims.swift`).

## First wave to pin (proposed — awaiting the creative director)

1. `kg.entity.select.inspector-shows-entity` (F2) — the live complaint: click an
   entity, inspector says "No selection".
2. `kg.entity.statements.loads-via-store` + `resyncs-on-change` (F3).
3. `kg.entity.source.one-anchor-builder` + `kg.entity.xsurface.same-anchor` (F5).
4. `kg.entity.rekey.on-focus-change` + `kg.entity.empty.no-claims` (D).

Everything else is the larger design, pinned in later waves.

## Design decision needed (creative director)

Where does the entity pane live when no document is selected? Two honest options:

- **(a) Entity arm on `DocumentInspector`.** When `document == nil` and
  `kgFocusState.focusedEntityId != nil`, render the existing `EntityDigestContent`
  (header · biography · appears-in · statements) for that entity — the inspector's
  own entity surface, already anchoring to source. Smallest change; one entity view.
- **(b) Filter the KG tab.** Key `KnowledgeGraphInspectorSection` on
  `focusedEntityId` and show only that entity's claims. Rejected as primary: that
  section is the *document's* graph (`documentKnowledgeGraph(documentId:)`), it has
  no document to load when a collection is selected, and it would mean a second
  entity-statements renderer beside `EntityDigestContent`.

Recommendation: **(a)**, with `EntityDigestContent`'s claim load moved onto
`ClaimStore.loadClaims(forEntity:)` so the pane and the ontology panel read the same
scope, and its rows kept on `ClaimSourceRequest.request(for:)`. The issue's proposed
`EntitySourceRequest` is not needed (F6).

## Findings (code evidence)

Paths relative to `fichero/fichero/`.

- **F1 — Entity → statements → source is already wired INSIDE a document.**
  `Views/Inspector/Knowledge/Entities/DocumentInspectorEntitiesTab+Rows.swift:56-59`
  (`entityDetailPane`) renders `EntityDigestContent` for the selected entity;
  `Views/Inspector/Knowledge/EntityDigestView.swift:679` loads
  `listClaims(entityId:)`; provenance rows post `ClaimSourceRequest.request(for:)`
  to `claimSourceNavigationState` at `:513-518`, biography sentences at `:345-351`.
  `Views/Inspector/Document/DocumentInspector.swift:98-102` switches to the Entities
  tab on `focusedEntityId`; `DocumentInspectorEntitiesTab+Actions.swift:22-28`
  selects the focused row.
- **F2 — No entity arm when no document is selected (the defect).**
  `Views/Shell/ContentView/ContentView+StateEvents.swift:140-149`: for the Entities
  collection (`isEntityLibrarySelection`) a selection focuses the entity and sets
  `detailDocument = nil`. `ContentView+StateSelection.swift:25-75` (`inspectorDocument`)
  then has no grid doc, no page focus, no sidebar folder (a KG collection is not a
  folder) → nil. `DocumentInspector.swift:85-89` renders `emptyState` ("No selection",
  `:147-152`). Same path from the force graph
  (`Views/Library/ViewModes/Graph/Ontology/ForceDirectedGraphView+Render.swift:107`) and
  the ontology list (`OntologyBrowser+List.swift:99`). `LibraryView+Selection.swift:319-326`
  tries to root `detailDocument` on a source document but only when that document is
  in the current listing — never true for a KG collection.
- **F3 — Digest bypasses the store and never resyncs.** `EntityDigestView.swift:670-690`
  calls `entityService.listClaims` directly and has no `claimStore.changeToken`
  observer (grep: 0 hits in that file). Contrast `OntologyBrowser+Detail.swift:38-47,
  73-90`, which loads via `claimStore.loadClaims(forEntity:force:)` and resyncs on
  `changeToken`. `ClaimStore.loadClaims(forEntity:)` is at `Models/ClaimStore.swift:104-115`;
  `changeToken` at `:65`.
- **F4 — The KG inspector section is document-keyed, not entity-keyed.**
  `Views/Inspector/Knowledge/KnowledgeGraph/KnowledgeGraphInspectorSection.swift:170`
  (`.task(id: documentId)`), `+Actions.swift:52-61` (`documentKnowledgeGraph(documentId:)`).
  It reads `kgFocusState` only to WRITE focus (`+Actions.swift:32-48`), never to filter.
  Keying it on `focusedEntityId` would require a document it does not have in the
  collection case — the reason option (b) is rejected.
- **F5 — Two anchor builders.** `Models/ClaimSourceRequest.swift:54-98` applies the
  precision rule (span > region > page-only; zero-length span = absent; fields carried
  only at the earned precision). `Views/Library/ViewModes/Graph/Ontology/Claim/ClaimSummaryCard+Details.swift:530-563`
  (`openClaimSourceRequest`) forwards `charStart/charEnd` and `bbox` unconditionally,
  with no `destination` and no precision. Callers of the second: `ClaimSummaryCard+Details.swift:301,371,438,579`,
  `OntologyBrowser+Detail.swift:28`, `KnowledgeGraphInspectorSection+Views.swift:122,142`,
  `EntityKindRow+ClaimBlock.swift:422-424`, `DocumentKGWebPaneCoordinator{MacOS,iOS}.swift:516/501`.
  The consumer (`ContentView+StateEvents.swift:397-448`) forwards whatever it is given
  as `charStart/charEnd/bbox`, so the two builders can differ on whether a highlight is
  drawn for the same claim.
- **F6 — `EntitySourceRequest` is not needed.** An entity has no location; each
  statement does, and the statement rows already anchor via `ClaimSourceRequest`.
  Opening the entity itself was ruled to be the scoped mention search
  (`DocumentInspectorEntitiesTab+Menus.swift:248-262`, `openEntity`). Deriving one
  anchor for an entity from "its claims" would pick an arbitrary page — the
  approximate-location class `ClaimSourceRequest` exists to forbid.
- **F7 — Backend is sufficient.** `Services/EntityService+Entities.swift:109`
  (`listClaims(entityId:limit:)`) → `GET /api/claims?entity_id=…`; no server change.

Existing coverage (kept, all pass today): `fichero/Tests/Unit/general/Models/KGFocusStateTests.swift`
(focus transitions), `Models/ClaimSourceRequestTests.swift` (precision rule),
`Views/Inspector/SourceNavigationContractTests.swift` (request shape),
`Views/Inspector/InspectorNavigationScopingTests.swift` (per-window cursor),
`Views/Inspector/KnowledgeGraphInspectorSectionTests.swift` (routing sweep),
`Views/Library/ClaimSummaryCardTests.swift`. Nothing pins the inspector showing an
entity without a document, the store routing of the digest's claims, the empty
state, or the same-anchor invariant.
