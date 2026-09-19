# Observable Data Layer — Design Spec (#TBD)

> Milestone: observable-data-layer
> Manual: TBD — contributor-facing only; the user manual needs nothing (this is a frontend
> architecture rule, not a user-visible surface).

> Design-led (Testing Constitution). Creative director owns intent; tests enforce it; code
> makes them pass. **Status: DRAFT — awaiting approval.** Written from a source-scan
> guardrail (#4824) that traced the same anti-pattern across many stores; this is that
> guardrail's spec anchor.
> Tags: **[OK]** built and tested · **[PARTIAL]** built, unproven or partly wired ·
> **[GAP]** intended, never built (needs an issue) · **[BROKEN]** regression, code
> contradicts the rule (needs an issue).

## Intent (the design)

The frontend has one reactive data layer, paraphrased from the standing architecture rulings:
a view never talks to the backend transport directly — it observes an `@Observable` domain
store and renders exactly what the store publishes. The store is the ONE endpoint accessor:
it loads once, then updates itself from the backend's per-library change-stream, from this
window, another window, a background workflow, or the agent, all the same way. When a store
mutates its own state — a save, a delete, an incoming change event — it updates the ONE item
that changed, in place, with a stable identity; it never rebuilds its whole published
collection for a change that touches one row. This exists because a wholesale rebuild is not
just wasteful — replacing a `List(selection:)`'s backing collection resets the user's
selection and can rebuild every row, which is what a minor edit "feeling overloaded," a list
that "flashes," and clicks that "land on the wrong row" all trace back to.

## Behaviors

- `observable.views-never-call-endpoints-directly` — **[PARTIAL]** a view must never call the
  generated OpenAPI client, construct a transport service, or otherwise reach the backend
  directly — only a store may. A real, working guardrail exists:
  `scripts/check_view_endpoint_access.py` scans the Views tree for `client.api.*` calls, raw
  `URLSession` use, and view-local service construction, exempting `*Store.swift`, `Services/`,
  WKWebView loads, and a documented set of sanctioned AppKit bridges. It is currently RED, not
  green: run for real (2026-09-18), it reports one NEW, unallowlisted violation —
  `LooveCoverage/LooveCoverageService.swift` calling `client.api.*` directly from a view — on
  top of an already-accepted `KNOWN_VIOLATIONS` migration backlog. No dedicated pytest file
  tests the checker itself; it self-verifies via its own baseline list, the same pattern
  `check_preview_coverage.py` uses. Filed #4825 for the new violation. Also tracked here:
  #3186 (Document Inspector's KG claims section still bypasses domain stores — the same
  violation class, KG-specific, found independently of the guardrail's own scan) and #1857
  (`DocumentKGWebPane`, a WebKit `NSViewRepresentable`, pushes deltas into the page via
  `evaluateJavaScript` on `updateNSView` today rather than OBSERVING entity/claim mutations
  through a store and reactively re-injecting — a reactivity gap on the WebKit-embed side of
  this same rule, not caught by `check_view_endpoint_access.py`'s Swift-only source scan).
  A sibling guardrail catches the same defect class a different way:
  `scripts/check_swift_hand_rolled_urls.py` scans for a literal `"/api/..."` engine path built
  by hand instead of routed through the generated client or a store — currently RED too, two
  new sites in `KnowledgeSettingsView.swift` (lines 132, 179), pre-existing (2026-09-07, not
  this week). Filed #4906 for that pair, cited here rather than restated as a second behavior,
  since it is the same rule caught by a second scan shape.
- `observable.store-mutator-updates-in-place` — **[BROKEN]** (#4824) inside a mutating method
  that changes ONE item — whatever the method is named; a lexical add/create/update/delete/
  remove/rename/move/promote/apply verb-list was tried first and missed `AnnotationStore
  .getAnnotation`, which reassigned the store's array exactly like its named siblings — a
  store must splice the affected item into its published collection in place — never call its
  own `reload()`/`refresh()`/`load…()`, never reassign the whole collection
  (`items = …`/`annotations = …`). The rule is now STRUCTURAL: every non-private method of a
  store class other than the load/reload/refresh family is scanned, regardless of its name.
  Verified BROKEN across the codebase, not a theoretical risk: `scripts/check_store_wholesale
  _reload.py`'s structural re-scan (2026-09-18) found **34 distinct (file, method) violations**
  (35 at last count, now 34 — `ClaimStore.delete`/`.link`/`.merge` and
  `InterpretationStore.create` fixed in the code lane's second batch, 169ca6299, and dropped
  from the allowlist) across `ActionStore`, `ArtifactStore.apply`, `AnnotationStore.apply`,
  `AuditStore`, `BackupStore`, `BatchStore`, `CitationStore`, `ClaimStore`,
  `InterpretationStore`, `KnownLibraryRegistryStore`, `NoteStore.apply`, `ReferenceStore`,
  `ResearchStore`, and `UsersStore` — seeded into `scripts/store_wholesale_reload_allowlist.json`
  as accepted debt pending fixes. `ArtifactStore.delete`, `AnnotationStore`'s five item
  mutators (including `getAnnotation`), all 7 of `NoteStore`'s create/update/delete mutators,
  and now `ClaimStore.delete`/`.link`/`.merge` and `InterpretationStore.create` are FIXED
  (b615abb14, splicing in place) and no longer appear in this count — the earlier 33-violation
  figure included them; today's 35 is the count with those removed and the structural re-scan's
  new finds added. Pinned:
  `test_check_store_wholesale_reload.py::test_fires_on_reload_call_inside_delete`,
  `::test_fires_on_whole_array_reassignment_in_update`,
  `::test_does_not_fire_on_index_splice_append_or_remove_all`,
  `::test_does_not_fire_inside_load_or_reload_itself`,
  `::test_handles_multiline_function_signature`,
  `::test_fires_on_get_method_that_reassigns_wholesale`,
  `::test_does_not_fire_inside_a_private_helper`,
  `::test_does_not_fire_on_a_non_store_class`, `::test_zero_stores_found_fails`,
  `::test_allowlisted_finding_passes`, `::test_stale_violation_entry_fails`,
  `::test_missing_class_field_fails`, `::test_violation_entry_without_issue_fails`,
  `::test_allowlist_entry_without_reason_fails`. **Also tracked here (legacy milestone fold,
  2026-09-19): #1973** — the beachball/spinning-cursor report is this behavior's user-visible
  SYMPTOM, not a separate defect: `LibraryChangeStream.route()` calls each consumer's `apply(_:)`
  synchronously on `@MainActor`, so any store still on the 34-violation allowlist above that
  calls a full `reload()`/`scheduleReload()` from inside `apply` stalls the main thread on every
  matching change event. Not independently re-verified against a live beachball this pass — the
  allowlist's own count (34 remaining violations) is the honest measure of how much of this
  symptom's cause is still live, not a guess.
- `observable.wholesale-replacement-only-on-identity-change` — **[OK]** this piece of the
  broader wholesale-reload work is fully built and tested even while the parent tracking issue
  stays open for the remaining violations: a store
  replacing its WHOLE published collection is only ever correct when the collection's own
  IDENTITY changed — its scope (which document/entity it is showing), its query (what a search
  matched), its sort order, or an explicit user-triggered resync. In every one of those cases
  there is no prior item to splice against, so a full re-fetch is the right behavior, not an
  instance of `observable.store-mutator-updates-in-place`. Read every flagged method by hand
  (not by name) to draw this line (2026-09-18 ruling): **13 distinct (file, method) methods are
  by-design** — `ArtifactStore`/`CitationStore`/`InterpretationStore`/`ReferenceStore.setScope`
  (pointing at a new document), `DocumentStore.selectCollection`/`.setLibraryLevel`
  (new folder/level scope), `DocumentStore.setListingSort` (new sort order),
  `SearchStore.performSearch`/`.applySearchResponse`/`.applySearchFailure`/`.resync` and
  `WorkflowStore.resync` (a new query or an explicit resync), and `ActivityStore.rebuildRuns`
  (re-derives the sorted run list from a fresh fetch). The allowlist enforces the line: a
  `by-design` entry requires a `reason` naming which axis changed, cites no issue, and is
  refused outright if the method's own name looks like a single-item mutator
  (add/create/update/delete/remove/rename/patch/merge/link/set…) unless that reason explicitly
  justifies it — `ClaimStore.setCuration` and `UsersStore.setActive`, both `set…`-named, were
  checked against this and are genuine violations (they patch one existing row, not the list's
  scope/query/sort), not by-design. Pinned:
  `test_check_store_wholesale_reload.py::test_by_design_entry_passes_and_is_not_counted_as_debt`,
  `::test_by_design_entry_without_reason_fails`,
  `::test_by_design_on_single_item_verb_without_justification_fails`,
  `::test_stale_by_design_entry_fails`.
- `observable.change-stream-applies-granularly` — **[PARTIAL]** (#4824) an incoming change-stream
  event should update only the row(s) it names, not trigger a scope-wide reload. Traced
  (2026-09-18): some stores genuinely do this — `ArtifactStore.update(id:documentId:content:)`
  splices the updated artifact into `items` by index; `AnnotationService`'s own
  `updateText`/`delete` methods splice correctly too (`AnnotationService+Update.swift:26`,
  `+Delete.swift:18`), and `ClaimStore.apply`'s `deleted` branch splices by id. But every
  `apply(_ event:)` this pass read still calls `scheduleReload()` for its `created`/`updated`
  verbs (and `ClaimStore.apply` also for `merged`/`linked`) — a full scope re-fetch, not a
  per-row splice — because (per `ArtifactStore`'s own doc comment) most domain events carry
  only `document_ids`, not item ids, so a cheap per-row splice from the event alone isn't
  possible today. These `apply` methods are classed `violation`, not `by-design`: an incoming
  event doesn't change the list's identity, it changes one row the list already contains. Open
  question below.
- `observable.no-per-item-refresh-loop` — **[BROKEN]** (→ #4696, sidebar-crud's own tracker,
  not this milestone's) a caller must never loop over several changed items calling a store's
  `refresh()`/`reload()` once PER ITEM — that is the same wholesale-rerender cost multiplied by
  the batch size. Verified: `SidebarActions.swift:224` (and `:85`) call `documentStore.refresh()`
  unconditionally inside a batch-delete loop. **No rule yet enforces this specifically** —
  `check_store_wholesale_reload.py` only scans a store's OWN mutating methods, not caller-side
  loops; a caller like `SidebarActions.swift` is structurally out of that guardrail's scope by
  design (see its own module docstring). Building a second guardrail for "a loop body containing
  a `store.refresh()`/`.reload()` call" was considered and NOT built this pass — proposed, not
  decided.

- `observable.failed-refresh-keeps-stale-rows` — **[OK]** (legacy milestone fold, 2026-09-19) a
  re-fetch that fails must never clear rows the store already loaded successfully — an artifact
  saved and visible must never vanish because a LATER refresh (a reconnect, a change-event
  resync) failed. `StaleDataPolicy.onFailure(isCancellation:loadedScope:requestedScope:)` is the
  one shared decision every affected store now routes through: `.ignore` when a newer selection
  superseded the request, `.keepStale` when the rows on screen belong to the scope that just
  failed to refresh (shown under an error banner — an honest report, not a silent fabrication),
  `.clear` only when the rows belong to a DIFFERENT scope than the one requested. Verified at
  HEAD: `ArtifactStore.reload()`, `InterpretationStore`, and `ObservableDomainStore` all call
  this same policy rather than each hand-rolling its own clear-on-failure logic.
  `ArtifactStore.setScope`'s own guard was fixed alongside it — it used to gate on
  `!items.isEmpty`, which a failed-but-kept-stale scope would satisfy forever and never retry;
  it now gates on `loadedScope == scope`, set only after a genuinely successful fetch. Pinned:
  `StaleDataPolicyTests` (9 cases covering ignore/keepStale/clear/cancellation/first-load/
  scope-identity), `ArtifactRunGroupingTests::testTheTotalityCheckWouldNoticeADroppedArtifact`.
- `observable.server-is-authoritative-not-client-computed` — **[GAP]** (#4427) a client renders
  server state and sends intents; it does not compute outcomes a second time locally, because
  the moment it does, every other client (another window, another device, a future non-Mac
  client) is wrong until it recomputes the identical logic — two clients with the same logic
  drift, two clients rendering the same server state cannot. This issue names two already-shipped
  defects of exactly this shape (a client-decided workflow scope, since fixed elsewhere in this
  session's own work) as evidence that the failure MODE is real, not hypothetical, even though
  the architectural principle itself has no single implementation to point at — it is a design
  direction for future real-time-sync work (drag an item in one client, see it move live in
  another), not a bounded, buildable behavior today. Cross-references this spec's own
  `observable.change-stream-applies-granularly` (change events carry only `document_ids`, not
  item-level state, which is a smaller instance of the same "server must say enough for a client
  to stay correct without recomputing" problem) rather than restating it.

## Redirect, not folded here

- **#4348** ("Artifact vanishes when the server connection drops mid-run") — **verify-close, not
  a live gap.** See `observable.failed-refresh-keeps-stale-rows` above: `StaleDataPolicy` now
  covers exactly this failure shape, pinned by 9 real tests plus a totality check. Evidence
  posted, left open, not closed here.

## Test matrix

| Leg | This surface? | Pins | File |
|-----|---------------|------|------|
| Guardrail (Swift source scan, run via Python) | y | no view calls the transport directly | `scripts/check_view_endpoint_access.py` (currently RED — see behavior above) |
| Guardrail (Swift source scan, run via Python) | y | a store mutator never reloads/reassigns wholesale | `scripts/check_store_wholesale_reload.py` + `fichero-server/tests/unit/scripts/test_check_store_wholesale_reload.py` |
| Backend (pytest) | n | the change-stream event SHAPE (item ids vs. scope-only) is an engine concern, not scanned here | — |
| Click-around (XCUITest) | n | "selection survives a delete" is exactly the symptom this rule prevents, but no dedicated flow test was found | — |

Hard-gate: `observable.store-mutator-updates-in-place` (the guardrail exists and is wired into
`verify_all.sh`'s `check_*.py` sweep by filename) once its allowlist debt starts shrinking
rather than only being tracked.

## Open questions

1. `observable.change-stream-applies-granularly`: artifact (and most other domain) change
   events carry only `document_ids`, not item ids. Does the fix belong on the ENGINE side
   (the event payload gains item-level ids) or the CLIENT side (a scoped re-fetch of just the
   named document's rows, still cheaper than the current full-scope reload)? #4824 raises this
   without resolving it.
2. `observable.no-per-item-refresh-loop`: worth its own guardrail (a source-scan for a
   `store.refresh()`/`.reload()` call inside a `for`/`ForEach` loop body), or is `SidebarActions.swift`'s
   instance narrow enough to fix directly without a new standing check?
3. Is `docs/contributor_manual/architecture/fichero/observable_data_layer.md` (the existing
   architecture doc `check_view_endpoint_access.py` already cites) folded into this spec, or
   do the two stay separate (architecture doc = the rule in prose, this spec = the rule made
   testable)?

**Answered 2026-09-18:** `SearchStore.applySearchResponse`/`.applySearchFailure`/`.performSearch`/
`.resync` reassigning the whole `results` array is BY-DESIGN, not a violation — a fresh search
or an explicit resync has no prior row to splice against (see
`observable.wholesale-replacement-only-on-identity-change` above). Filed as its own allowlist
class rather than a special-cased exemption from the mutating-verb scan.
