# Sidebar & Library review — selection, performance, data ops (2026-08-08)

Scope per Daniel: top-to-bottom review of sidebar + library for bugs, speed,
selection correctness; measured, not guessed. Trace: `profile/Aug 5 2.trace`
(read-only). Milestones consulted: 77, 116, 117, 165, 180, 238, 269.

## Measurements (this trace, exported via xctrace)

- **300 potential hangs, 91.4 s total main-thread stall** in a 406.7 s session
  — the app is unresponsive **22% of the time**. Worst: 6.54 s @ 06:40,
  2.99 s (Severe) @ 00:21. Clusters: 02:13–02:34 and 04:36–05:02.
- **399 hitches.**
- **SwiftUI instrument tables are EMPTY again** (`swiftui-updates`,
  `swiftui-causes`: schema only, zero rows) — the 4th consecutive trace.
  #4547 stays open; every attribution below is Time-Profiler-based (aug4):
  context menu 506 samples, SidebarItemRow copies ~740, Document == 210,
  LibraryView.body 230, SidebarView.body 140.

## Fixed this session (needs Daniel's build to verify)

1. **#4546** `d23bf7864` — hand-written `Document ==`/`hash`; skips the six
   blob fields (safe: server writes bump `updated_at`; only `status`/`sortOrder`
   mutate in place client-side, both still compared). Mirror-based inventory
   test forces a decision for any new field.
2. **#4544 + #4556 (mechanism half)** `c3aef4501` — context menu construction
   deferred to menu open via `SidebarDeferredMenuContent`; pin test forbids the
   bare form. First-right-click completeness needs a live check.

**Verify with:** re-trace the same session shape and compare `potential-hangs`
totals (`xcrun xctrace export --xpath '…table[@schema="potential-hangs"]'`);
the aug4 attribution predicts the context-menu samples vanish from row render.

## Selection architecture — answer to "click → select → view update?"

The pipeline IS click → select → route: `List(selection:)` binding setter
(derives primary via `sidebarPrimaryDestination`) → `.onChange` →
`handleSelectionChange` → `sidebarMode`/`viewMode`. Design is sound; found
four defects around it:

- **S1. Per-row tap fallback** (`SidebarItemRow+Presentation+Body.swift:39`,
  #645/#1165): every row carries a `simultaneousGesture(TapGesture)` that
  schedules an async `Task` per click — a second selection write path and a
  gesture recognizer per row. It predates the resilient binding-setter
  (#4297); likely removable now, but that needs a live click-through test
  (icon/text clicks were the original failure).
- **S2. Library switch ordering** (`handleLibrarySwitching`): writes
  `windowState.libraryId` then routes immediately; the comment admits the
  environment needs "next run loop". Cross-library selection can route
  against the OLD library's services. Needs a deferred route or a
  library-ready gate.
- **S3. Focus ambiguity is real and unaddressed**: sidebar and library are two
  selection domains (correct post-#4552), but no surface says which one is
  focused. Matches already-filed #1841 (right-clicked ≠ selected focus ring)
  and #1951 (selection greys when unfocused). Daniel's "hard to know what is
  properly selected" = these two.
- **S4. `allCachedItems: [SidebarItem]` is a stored property of EVERY row**
  (#4545's biggest slice): the whole forest array is copied into each of N
  rows per render, and any forest change invalidates every row. It serves
  only parent/ancestor lookups (`findItemById` — a WALK, though an O(1)
  `cachedItemIndex` already exists). Fix: inject a `(String) -> SidebarItem?`
  lookup closure backed by the index. Cuts row size, false invalidation, and
  the walk. Probably also most of #4522's residual whole-sidebar redraw.

## Delete-parent bug (Daniel: "I delete children and the parent is deleted")

Mechanism found: `handleDeleteSelection` (SidebarActions.swift:114) deletes
`selectedItems` — the **sidebar** selection — and it is wired to the bottom
toolbar delete button and ⌘⌫ unconditionally. When the user's working
selection is child rows **in the library grid**, the sidebar still holds the
PARENT folder; the delete deletes the parent. Two required fixes:
1. Route delete by **focused surface** (the same law as #4552's run scope).
2. The confirmation must **NAME the targets** ("Delete 'EAP1740_NP…' and 2
   more?"), never a bare count — a proper error/confirmation surface would
   have made this bug visible on first occurrence.

## Children arrive slowly / preload

- Expand does a one-level load + grandchild prefetch (#4293); root-level
  prefetch happens at `loadCollections`. The felt slowness has two measured
  causes elsewhere: **#4205** (one serial GET per imported document during
  catch-up) and **#4549** (embedding computed inline during ingest starved an
  unrelated `get_children` to 24.8 s — engine log 2026-08-05). Fixing #4549
  and batching #4205 is the preload that matters; deeper eager prefetch of a
  large tree would fight the engine for the same contended resource.

## Other findings

- **Bottom status bar**: `shouldShowBottomToolbar` is hardcoded `true`
  (`SidebarView+ViewComponents.swift:38`). Daniel wants it gone or
  library-scoped; #3404 (remove duplicate bottom status/location bar) is
  already filed — treat as one decision.
- **Two hit targets per row** (row + name hover): `fullWidthLabel` carries its
  own `contentShape`/hover/`.help` inside the row's outer contentShape, plus
  the trailing hover open-affordance (#2496). Deliberate layering, but it
  reads as two targets; UX decision needed with #4476 (two row-height
  mechanisms).
- **Beachball on click** during change-stream bursts is filed as **#1973**
  (consumer `apply()` blocks main thread) — milestone 77, relevant to the
  hang clusters.
- **Per-pane title bars** (Daniel's ask: each preview/reader says what it
  shows, single vs multiple) — fits the #4525 PaneContentPlan seam; new issue
  needed.
- **Library drop-in zoom animation** (items animate from top on import;
  sidebar rows just appear): not yet located; next fix-pass item, look at the
  grid's implicit animation/transition on `currentDocuments` insertions.
- **PDF selection unreliable**: #4558/#4559 territory (parent-id guard +
  whole-doc reader payload); two-stack fix planned separately.

## Measurement discipline going forward

- `scripts/gate part sidebar` after each change (perf ratchet is automatic).
- #4550 hang ratchet is viable NOW from `potential-hangs` (a small export, no
  2.7 GB parse); SwiftUI-metric ratchet is NOT (tables empty, #4547).
- Ask: a fresh trace after this session's two commits, same session shape,
  for a before/after hang-total delta.
