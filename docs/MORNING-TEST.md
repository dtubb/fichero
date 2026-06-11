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
