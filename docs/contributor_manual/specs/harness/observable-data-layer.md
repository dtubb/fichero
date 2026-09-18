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
  `check_preview_coverage.py` uses. Filed #4825 for the new violation.
- `observable.store-mutator-updates-in-place` — **[BROKEN]** (#4824) inside a mutating method
  (add/create/update/delete/remove/rename/move/promote/apply), a store must splice the
  affected item into its published collection in place — never call its own
  `reload()`/`refresh()`/`load…()`, never reassign the whole collection
  (`items = …`/`annotations = …`). Verified BROKEN across the codebase, not a theoretical
  risk: `scripts/check_store_wholesale_reload.py` scanned 38 `@Observable` store classes and
  found 33 distinct (file, method) violations, seeded into
  `scripts/store_wholesale_reload_allowlist.json` as accepted debt pending fixes —
  `ArtifactStore.delete`/`.apply`, `AnnotationStore`'s five mutators + `.apply`, and 26 more
  across `ActionStore`, `BackupStore`, `CitationStore`, `ClaimStore`, `InterpretationStore`,
  `KnownLibraryRegistryStore`, `NoteStore` (all 8 of its mutators), `ReferenceStore`,
  `ResearchStore`, and `UsersStore`. Pinned:
  `test_check_store_wholesale_reload.py::test_fires_on_reload_call_inside_delete`,
  `::test_fires_on_whole_array_reassignment_in_update`,
  `::test_does_not_fire_on_index_splice_append_or_remove_all`,
  `::test_does_not_fire_inside_load_or_reload_itself`,
  `::test_handles_multiline_function_signature`,
  `::test_does_not_fire_on_a_non_store_class`, `::test_zero_stores_found_fails`,
  `::test_allowlisted_finding_passes`, `::test_stale_allowlist_entry_fails`,
  `::test_allowlist_entry_without_reason_fails`.
- `observable.change-stream-applies-granularly` — **[PARTIAL]** (#4824) an incoming change-stream
  event should update only the row(s) it names, not trigger a scope-wide reload. Traced
  (2026-09-18): some stores genuinely do this — `ArtifactStore.update(id:documentId:content:)`
  splices the updated artifact into `items` by index; `AnnotationService`'s own
  `updateText`/`delete` methods splice correctly too (`AnnotationService+Update.swift:26`,
  `+Delete.swift:18`). But every `apply(_ event:)` this pass read calls `scheduleReload()` for
  `created`/`updated`/`deleted` verbs — a full scope re-fetch, not a per-row splice — because
  (per `ArtifactStore`'s own doc comment) artifact events carry only `document_ids`, not item
  ids, so a cheap per-row splice from the event alone isn't possible today. Open question below.
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
2. `SearchStore.applySearchResponse`/`.applySearchFailure` reassign the whole `results` array
   on every search — flagged by `check_store_wholesale_reload.py` but NOT asserted here as a
   violation: a fresh search legitimately has no prior row to splice against, so replacing the
   whole result set may be the correct behavior for this one store, not an instance of the
   rule this spec pins. Needs a ruling on whether "apply" as a mutating-verb match should
   exempt a store whose entire job is producing a NEW result set each call, or whether this
   genuinely regresses selection the same way the others do.
3. `observable.no-per-item-refresh-loop`: worth its own guardrail (a source-scan for a
   `store.refresh()`/`.reload()` call inside a `for`/`ForEach` loop body), or is `SidebarActions.swift`'s
   instance narrow enough to fix directly without a new standing check?
4. Is `docs/contributor_manual/architecture/fichero/observable_data_layer.md` (the existing
   architecture doc `check_view_endpoint_access.py` already cites) folded into this spec, or
   do the two stay separate (architecture doc = the rule in prose, this spec = the rule made
   testable)?
