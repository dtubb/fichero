# KG Interactions, Standards & Cross-Surface Testing — Design Spec (#4643 · #4641 · #4636)

> Design-led (Testing Constitution). Creative director owns intent; tests enforce it.
> **Status: DRAFT — awaiting approval.** An AREA spec (per the "split by area" ruling,
> 2026-09-09): interaction + standards + test-leg concerns for the KG tables live here, so
> `kg-tables.md` (CRUD/filters/scale) stays focused. Tags: [OK]/[MISSING]/[PARTIAL].

## Audit — what the KG tables have vs. a first-class Mac library view

- **Drag & drop** [MISSING] — the *document* table is draggable (`.draggable(libraryItem
  Drag…)`); the **KG tables are not**. An entity/claim should drag (into a note, a
  workspace, another folder, the canvas) and accept drops where meaningful.
- **Contextual menu (right-click)** [PARTIAL] — entities: bless/reject/retype/merge/delete/
  edit/rename. claims: edit/delete. **Missing:** claim **merge/combine**, **comment/
  annotate** on both, and a shared full verb set.
- **Shift/multi-select → act** [PARTIAL] — Set selection gives range-select; a selection
  can be deleted/curated, but **cannot yet be EXPORTED** (e.g. selected rows → JSON-LD /
  JSONL / CSV). "Select 200 claims, export as JSON-LD" is the target.
- **Claim richness surfaced** [MISSING in UX] — the `KnowledgeClaim` model is already deep:
  provenance (`provenance_layer`, `attribution_chain`, `created_by`, `model`/`provider`,
  `editor`/`scribe`/`speaker` name+entity), place (`claim_geo`, `claim_location`,
  `place_values`), time (`claim_recorded_at`, `date_values`, `time_start`/`end`/
  `precision`, `temporal_context`), anchor (`source_anchor`, `source_char_start`/`end`,
  `source_segment_id`), argument (`grounds`/`warrant`/`backing`/`rebuttal` — Toulmin),
  `translation_chain`, corroboration. **The table shows only S·V·O/date/source/confidence.**
  Surface the rest (inspector detail + optional columns), editable, provenance-tagged.
- **Versioning** [MISSING] — no history/revision endpoints for claims/entities; only
  `updated_at` + `merged_into_id` + the MutationLog (undo). Full restorable per-record
  version history is the #4636 model — not built. "Do all the versioning" needs it.

## Behaviors to add

### Interactions
- `kg.interact.drag` — entities + claims are `Transferable`; drag into note/workspace/
  canvas/folder; the drag payload carries the id + a standard serialization (JSON-LD item).
- `kg.interact.drop` — a table accepts drops that make sense (a claim onto an entity links
  them; a doc onto the claims table scopes/creates).
- `kg.interact.context-menu-full` — one shared right-click verb set: open · edit · rename ·
  **merge/combine** · bless/reject/retype · **comment** · delete · **export selection…**.
- `kg.interact.comment` — a human comment/note on a claim or entity (distinct from a claim);
  authored + dated + provenance-tagged; a review/collaboration affordance.
- `kg.interact.export-selection` — shift-select rows → export as **JSON-LD** (validated,
  #4641) / JSONL / CSV; the selection is the scope.
- `kg.interact.keyboard` — ⌘⌫ delete · ⌘A select-all · ⏎ open · F2/double-click rename
  (shared selection grammar, #4436).

### Standards coverage (is it all in the design?)
- Anchors → W3C Media Fragments / Web Annotation (#4635); Claims/entities → RDF, JSON-LD,
  Linked Art, CIDOC-CRM (#4641); provenance → W3C PROV (#4636); authority → VIAF/Wikidata/
  GeoNames/Getty/Pleiades/PeriodO (#4641, all selectable); editions/reading-order → TEI/
  METS/IIIF (#4638/#4635). **Yes — the standards are speced across the area specs; this doc
  is the interaction/export surface for them.**

### Versioning (surfacing #4636 in the tables)
- `kg.version.history` — a claim/entity shows its version history (who/model/when/reason/
  cost — #4636) and can restore a prior version.
- `kg.version.author-mark` — hand vs AI vs enriched-from-<source>, at a glance.

## Cross-surface / cross-platform test matrix (the "are they ALL testing?" answer)

Every behavior ships tested on the legs it touches, or it is not done:

| Leg | Today (KG) | Required for the above |
|---|---|---|
| Swift unit | ✅ pure-rule + availability + transport | pure rules for drag payload, export mapping, version diff |
| Backend pytest | ✅ CRUD + contracts | batch-delete, export serialization+validation, version history, comment |
| MCP | ✅ create/delete/query | comment, export, merge, version read via MCP |
| CLI | ⚠️ dedupe + claim CRUD | export selection, merge, comment, version parity |
| **Mac XCUITest** | ⚠️ inspector-load (flagship navigation+render test) only | `performAccessibilityAudit()` on the KG surfaces; NOT table CRUD (see correction below) |
| **iPad/iOS** | ❌ canary only | the touch path for the KG tables (#4250 CLI/MCP/iOS legs) |
| Load/background | ❌ (#4634) | delete/export 1k–10k bounded, no peg |

**Correction (verified this session, 2026-09-13): table CRUD is the WRONG layer for Mac
XCUITest.** XCUITest cannot reliably drive SwiftUI context-menu item activation on macOS
(the menu opens, but `.tap()` on a menu item does not fire it) or `.draggable`/
`.dropDestination` drags (the gesture performs no real NSDragging session). So
"select→delete/edit/rename/merge…end-to-end" and "click delete → row gone" — anything
routed through a context-menu verb or a drag — must NOT be pinned as an XCUITest
requirement; that test would be unreliable/flaky by construction, not by lack of effort.
These CRUD behaviors are pinned at the **ACTION/UNIT layer** instead: drive the store/model
method directly (e.g. the delete/edit/rename/merge action on `EntityStore`/`ClaimStore` or
equivalent) and assert the resulting observable state (row/claim gone, renamed, merged) —
this is exactly what "Backend pytest ✅ CRUD" and "Swift unit ✅ pure-rule + availability +
transport" above already cover for their layers, and is what worker: MCP/CLI legs also test.
Mac XCUITest's reliable job for the KG tables is **navigation + rendering** (does the
inspector load and show the right content — the flagship inspector-load test) and
`performAccessibilityAudit()` (labels/traits/contrast), not driving context-menu verbs or
drags.

**Priority test gaps:** action/unit-layer coverage for KG table delete/edit/rename/merge
(store-level, not XCUITest), comment, and export selection; the iPad/iOS touch leg (which
uses native touch gestures, not context-menu `.tap()`, and may not hit the same XCUITest
limitation — unverified, needs its own check before assuming XCUITest works there either).
Ties #4542 (wire `ux_smoke.py` into the gate), #4250 (iPad/iOS/CLI/MCP legs), #4634 (load).

## Open questions
- Comments: a first-class `Comment` record (threaded?) or a claim of a "comment" type?
- Drag payload: JSON-LD item vs an internal id — or both (internal for in-app, JSON-LD for
  out)?
- Which extra claim fields become table COLUMNS vs inspector-only (columns cost width)?
