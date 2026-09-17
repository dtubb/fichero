# Morning Report — overnight of 2026-09-16 → 17

Manager: Claude (Opus 4.8). Daniel out ~16:00, back in the morning. Local commits only (not pushed).
Newest section on top. **What to look at is in ⭐ LOOK AT.**

---

## ⭐ LOOK AT (updated ~17:00)

1. **Re-run in Xcode (⌘R)** and verify (commits `dfa937946` + `3d54db5b5`):
   - **Panes**: no crash on split/resize/⌘⌥1–5; Read = one library; **split then close one → only that one closes**;
     Transcribe/Tall/Compare library strip is a narrow ~72px film-strip; pane-head far-left icon switches kind;
     library/reader/chat panes have **no hairline** under the head (liquid glass like Preview).
   - **Reader overlays**: highlights / bounding boxes / OCR readings now stay in the right spot on **flipped or
     auto-cropped** pages (they were drawing over re-framed pixels). Try a page you've flipped/auto-cropped.
   - **Menus**: ⌘F Search, ⌘⌥F Find in Page, ⌃⌘F full-screen, File ▸ Import holds New Folder + Import.
   - **Loupe** doesn't pop on ⌘⌥1.
2. **Open questions** for you are at the bottom.

## DONE + COMMITTED
- `dfa937946` — one-system workspaces: seed PaneList (fixes two-libraries/close-both), 5-set
  (Read/Browse/Transcribe/Transcribe·Tall/Compare; dropped Catalogue/Claims), crash fix, 72px film-strip,
  split-close reorder, kind-switcher, sole-pane head collapse, liquid-glass head convergence, Search/Find-in-
  Page/Import→File menus, loupe Option-only. Tests included. Build green.
- `3d54db5b5` — reader overlay frame-identity: `frameChangingOps` now covers flip_horizontal/flip_vertical/
  auto_crop_border (the missing ops that misplaced overlays). +regression tests. +DRAFT spec
  `reader-overlay-frame-identity.md`. Synced panes + menus specs to built code (both DRAFT). Build green.
- `4e9ea64e3` — Settings ▸ AI ▸ Defaults now uses the shared one-step picker (`SettingsSharedModelPicker`,
  SharedModelRow) instead of the Provider→Model drill-down; parity test updated. Build green.
- `21820e8d2` — Chat toolbar picker uses the shared builder + SharedModelRow (was raw Text menu). Build green.
- `9388a2679` — NODE popover model selector uses the shared one-step picker (the last forbidden
  Provider→Model drill-down is gone). Build green. ⚠ Worth a click-test: node model pick defers the
  model binding one hop to beat the provider's auto-first-model — verify the pick sticks.

- `d184f1d10` — kg-entity-inspector pinning tests (6 behaviors) + fixed Swift Testing comment literals
  (concatenated → single literal) so the test target compiles. **TEST BUILD green + all new unit suites
  RUN GREEN** (RenditionEditStates, PaneInstanceIndependence, BuiltInWorkspaceLayout, MenuShortcut-
  Uniqueness, EntityInspectorPinning, NodeModelListParity). Tonight's tests are runtime-verified.

- `5559a5908` — workflow-node-config safe fixes: **F13** Compare-Models Apply now updates the picker chip
  (was ignored until reopen — looked like Apply did nothing); **F9b** alias/Apple canvas node subtitle no
  longer blank. +5 tests, green.

### workflow-node-config triage result
- ALREADY FIXED (prior `719094241` + tonight's shared pickers): F1 effective/ghost prompt, F2 transcribe
  llm-gating, F4 default-is-ghost/open-is-read-only, F6 usesLLM stable, F7 node list == Settings list.
  Tonight: F13, F9b. → spec markers being flipped to [OK].
- NEEDS YOUR EYES (design/UX or cross-repo — I did NOT touch): F3 auto-mode chip label; F11 stale removed-
  provider warning; F5 folder/collection prompt (server-side, "is the prompt editable?" decision);
  F8 vision-requirement-from-server (needs a server flag); F16 kraken model field; F9a canvas icon/color
  registry drift; E section config-summary row.
- SAFE, doing next: F5/entities (add the prompt editor — component exists, server honors it);
  F4-residual (transcribe legacy-language normalise writes config on open — subtle).

- `a265cf7f3` — entities node gets the shared prompt editor (F5/entities, server already honored it);
  workflow-node-config.md markers synced to reality (F1/2/4/6/7/13/9b → OK, read-only kept partial). +test.

- `f519e4503` — transcribe node: opening no longer rewrites legacy language (F4-residual). +test.
- `eadc556dd` — Search node: opening no longer rewrites search_id/query. **open-is-read-only now fully
  [OK]** (prompt + transcribe + search all guarded on load, pinned). +test.

**10 commits tonight, every one build-green and unit-tested (where testable). open-is-read-only closed.**

## ⚠ MEMORY CONSTRAINT (as of ~17:15)
- Machine is swap-thrashed (76MB free RAM, swap 15.1/15.3GB used). `build-for-testing` keeps getting
  SHED by the OS. Builds are paused until it recovers. If it doesn't recover on its own, closing other
  apps (or a reboot) frees it — my own agent process holds ~1GB.

## UNCOMMITTED (done on disk, awaiting a green build to commit)
- New DRAFT spec `reading-markup-annotations.md` (annotation kinds, the ✓→✓✓→✓✓✓→clear check cycle,
  rating-is-a-check, review-grouped-by-page, promote-to-claim, W3C export; behaviors grounded in engine
  + Swift code, most already tested).
- `AnnotationCheckCycle` — extracted the check-cycle to ONE pure testable enum; routed both interaction
  sites (ZoomableImagePreviewMac+Annotations, RegionInteractionLayer) through it. +`AnnotationCheckCycleTests`.
- Will commit as soon as a build passes.

## IN FLIGHT (workers)
- (idle — builds paused for memory)

## NEXT / REMAINING
- **⚠ VISUAL CHECK (held for you, not done blind):** island adopts its own SharedModelRow; workflow-bar
  row; retire the leftover Downloads tab (folds embeddings into a provider row); node-model-pick defer
  (5559a5908/9388a2679 — verify the pick sticks).
- **agent-work → new spec** (your queue item 5): mine agent-work/ for something unspecced, draft a spec,
  test it. Doing this next (safe doc work).
- Other spec debt: kg-tables (8 missing — build + test, riskier), other DRAFT specs to finish + cite tests.
- workflow-node-config NEEDS-EYES: F3 auto-mode chip label, F5 folder/collection prompt (server decision),
  F8 vision-from-server, F9a canvas icon/color registry drift, F11 stale-provider warning, F16 kraken field.

## QUEUE (priority)
1. **Model / AI-inspector move** (per your #1): Settings + island + chat + nodes all use ONE picker
   (`SharedModelListBuilder`/`SharedModelRow`), killing the Provider→Model drill-down in Settings. Plan ready
   (two rival spines found; Spine B drill-down is what the ratified ruling forbids). AI-settings redesign is
   ~60% landed (provider peer rows + inline downloads + one catalog); remaining = retire the leftover Downloads
   tab + unify catalog-add rows onto SharedModelRow.
2. **kg-entity-inspector**: near-done spec — add the pinning tests its header names (F3 loads-via-store,
   resyncs-on-change, select routing, rekey) → flip toward DONE.
3. **workflow-node-config**: APPROVED but 15 broken behaviors (prompt gating, model-list≠Settings,
   open-is-not-read-only) — fix + pin each. Biggest live-regression surface.
4. **Reader-overlay follow-ups** (from the new spec): engine stamps `frame_status` (delete the hand-list);
   fail-closed on unknown ops; frame-gate the PDF mark layer.
5. Finish other incomplete specs + citing tests (see spec audit below).

## SPEC AUDIT (both guardrails GREEN; 8 APPROVED, 14 DRAFT)
- DONE: `ui/sidebar-crud.md` (only fully-complete spec), `testing/xcode-build-configs.md` (near).
- NEARLY: `kg/kg-entity-inspector.md` (needs tests), `transport/transport-http-uds.md`, `testing/ui-test-harness.md`.
- HEAVY DEBT (code, not prose): `ui/workflow-node-config.md` (15 broken), `ui/panes-workspaces.md`
  (several gaps closed tonight), `kg/kg-tables.md` (8 missing).
- DRAFT proposals to ratify+test: `menus-and-commands.md`, `model-selector-consistency.md` (both updated tonight).

## OPEN QUESTIONS (for the morning)
- **Sidebar chat type-switch**: chat isn't a PaneList leaf (deliberate) → no leaf to switch. Promote it to a
  real pane, or leave as-is? (Left as-is.)
- **"Bar only if asked"**: I made the head hairline opt-in (default off). Want the whole filter/sort strip
  hidden by default too (that hides quick filter/sort access)? Say the word.
- **Ratifying specs**: `menus-and-commands` + `model-selector-consistency` are DRAFT proposals now matching
  much of the built code — want them flipped to APPROVED (adds test/milestone guardrail requirements)?

## NOTES / RISKS
- `Version.xcconfig` (2026.09.15→.16) left uncommitted — Xcode version-stamp, not my work.
- ~78 uncommitted docs/user_manual reorg files predate this session — untouched, uncommitted.
- Legacy `WindowLayoutPreset` type still exists (menus no longer show it); full deletion is a later cleanup.
