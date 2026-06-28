# TEST IN THE MORNING — overnight run 2026-06-10 → 06-11

Things the autonomous overnight run built that need Daniel's **visual / runtime** check
(I compile-verify + unit-test, but can't see the GUI or click). Newest at top.

## Awaiting visual/runtime verification
- **#2009** Interpretations panel — live-updates as interpretations are created/edited (other windows too).
- **#2003 / #2004 / #2005** Track B — artifacts / citations / references as List + detachable detail window (click → detail follows selection; "Open in Window" tear-off; draggable).
- **#1973** beachball on click (should be fixed by the observable extraction emits — confirm no spinning cursor).
- **#2006** ContentView frame-warning (cosmetic console warning).

## Built overnight (added as the run proceeds)
<!-- the loop appends: feature → issue → how to test -->
- Merge two entities (Ontology Browser → select absorber → "Merge N entities") — should still merge correctly AND now write an audit row (#1848 exhibit A: UI button now routes through `POST /api/actions/invoke` `entity.merge`); verify no regression.

## #1848 frontend remainder — SHIPPED 2026-06-11 (needs click-verification)

- **Mutation buttons now go through the audited action path** (#1848): verify each still works AND that ⌘Z can undo it (single-level):
  - **Claim**: delete a claim; edit a claim (EditClaimSheet/InlineClaimEditor "Save" → `claim.patch`).
  - **Document**: delete a document (sidebar / ⌘⌫).
  - **Annotation**: delete an annotation (Document Inspector → Annotations tab).
  - **Note**: delete / edit a note (Document Inspector → Notes tab, and Notes browser).
  - Each should behave as before; the win is they're now audited + ⌘Z-undoable.
- **App Intents / Shortcuts (#2017)** — open **Shortcuts.app**, "+" a new shortcut, search **"Fichero"**. You should see curated actions: **Merge Entities, Create Note, Delete Document, Run Workflow, Create Annotation**. Run one (e.g. Create Note) and confirm it hits the running engine and writes an audit row. (Also should surface in Spotlight.)

## Track B Phase 2 — Annotations + Notes as List + detachable detail (#2010, #2011) — SHIPPED 2026-06-11

Same recipe as #2003/#2004/#2005 (artifacts/citations/references):
- **Annotations** (Document Inspector → **Annotations** tab): now a **List** (click a row → selects) with a **detail** view that follows selection. There should be an **"Open in Window"** tear-off that opens the annotation in its own window and tracks the selection. Confirm: clicking selects; detail updates; tear-off window follows; delete/edit still work (and are ⌘Z-undoable via the audited path).
- **Notes** (Document Inspector → **Notes** tab, and the **Notes browser**): same — List + detail + tear-off WindowGroup. Confirm click-select, detail-follows, tear-off, and delete/edit.

## ⌘Z undo of the last audited action (#2015)

After merging two entities, press **⌘Z** — the merge should undo (the entities
un-merge). Single-level for now: ⌘Z reverses only the most recent audited action,
then the menu item disables until another action is invoked. Multi-level undo
(walking the audit log) is a follow-up.
