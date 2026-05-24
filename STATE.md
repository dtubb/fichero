# STATE.md — Fichero

## Snapshot

**Branch:** `0.0.2`

## Current Focus

1. **Entity Platform** — Inspector panel, biography/digest views, five-pane reading layout.
2. SwiftUI implementation of entity inspector (persistent rightmost pane, #1199).
3. Autoloop handling backend entity issues (#1185 done, #1192, #1193 pending).

## In Progress

- Autoloop running in `tmux:fichero → autoloop` — entity platform backend issues (#1192, #1193).
- Five-pane SwiftUI reading layout (#1189): sidebar | page-list | PDF | content | inspector.
- Persistent inspector architecture (#1199): stable rightmost pane across all views.

## Blocked

- OpenRouter weekly key quota can hard-stop remote vision/extraction runs (`403 Key limit exceeded`) on some libraries.

## Next Session — Start Here

1. **Entity platform HTML prototypes committed** (commit `c366b2c4`): publication-view.html, entity-digest.html, entity-library.html, book-view.html all in `.superpowers/brainstorm/43871-*/content/`.
2. **KnowledgeClaim fields shipped** (#1185 done): `claim_location`, `temporal_context`, `claim_speaker` in model + openapi.json synced.
3. **SwiftUI implementation priority order** (start here for Mac app):
   - #1199: Persistent inspector layout (architectural anchor — stable rightmost HStack column across all views)
   - #1189: Five-pane layout (sidebar 240px | page-list 120px | PDF flex | content 200px | inspector 340px)
   - #1190: Entity inspector Text mode (dense semicolon digest format)
   - #1197: Bidirectional three-pane sync (`ClaimFocusState` observable at window level)
   - #1196: Page-scoped KG graph in Map tab (8-node default, scope pills)
   - #1194: Book reading view
4. **Autoloop queue**: issues #1192 (svo_verb prepositions) and #1193 (CLI entity commands) in `agent-work/queue.md`, status pending.
5. **GitHub milestone**: New entity platform issues (#1183–#1199) are on "Epistemic Platform Expansion" milestone (#6).
6. Backend tests baseline: 2926 passed, 21 skipped, 21 xfailed — healthy.
