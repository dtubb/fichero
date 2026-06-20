# Lane A — Per-page transcription scope — FINDINGS (#2303 #2395 #2396)

Branch `worker/perpage-transcription`. Do NOT push. Manager integrates.

## Root cause

In `process_vision` (`fichero-engine/src/fichero/workflows/tools/vision_base.py`),
the `_whole_pdf_parent` guard was:

```python
_whole_pdf_parent = (
    resolve_path_to_doc(path_to_doc, file_path) if per_page_texts else None
)
```

`per_page_texts` is a list — populated with **all** pages for the whole-PDF path,
but also populated with a **1-element list** for the per-page fan-out path
(Apple Vision single page, born-digital text layer for a single page, LLM single page).

When `per_page_texts` had 1 element (truthy), `_whole_pdf_parent` was set to
the **parent PDF's** document ID regardless of whether we were in per-page
fan-out mode. Then `_propagate_to_page_children` was called with that parent ID
and a 1-element `page_texts` list. `_propagate_to_page_children` writes by
sequence-indexed position:

- Page child with sequence=1 → `page_texts[0]` = page N's text → **wrong content, wrong page**
- Page child with sequence=2 → index 1 >= len 1 → skipped
- Page child with sequence=3 → index 2 >= len 1 → skipped

Effect:
- Transcribing page 2 of a 3-page PDF wrote page 2's content to page 1 (#2396).
- Pages 2 and 3 never received their correct content (#2395/#2303).
- Artifact on page 1 contained the wrong text; pages 2 and 3 had no artifact.

## Fix

One-line guard change in `vision_base.py` ~line 1987:

```python
# Before
_whole_pdf_parent = (
    resolve_path_to_doc(path_to_doc, file_path) if per_page_texts else None
)

# After
_whole_pdf_parent = (
    resolve_path_to_doc(path_to_doc, file_path)
    if per_page_texts and requested_page_index is None
    else None
)
```

`requested_page_index is None` is only true when the whole PDF is processed at
once. For per-page fan-out, `_whole_pdf_parent` is `None`, so the code falls
through to `save_artifact` with `doc_id_for_file` — the page child's own ID.

## Files changed

| File | Change |
|------|--------|
| `fichero-engine/src/fichero/workflows/tools/vision_base.py` | Add `and requested_page_index is None` to `_whole_pdf_parent` guard |
| `fichero-engine/tests/unit/test_transcription_save.py` | 3 new regression tests in `TestPerPageFanOutSaveRouting` |

## Tests added (`TestPerPageFanOutSaveRouting`)

1. `test_per_page_fanout_saves_to_page_child_not_parent` — regression: per-page fan-out
   must call `save_artifact(document_id=page-2-id)` and must NOT call
   `_propagate_to_page_children`. Goes RED on old code.
2. `test_whole_pdf_path_still_propagates_all_pages` — whole-PDF path must still call
   `_propagate_to_page_children` with all 3 page texts. Ensures fix doesn't break the working path.
3. `test_siblings_untouched_when_page2_transcribed` — #2396: transcribing page 2 saves
   only to page-2-id; page-1-id and page-3-id are never written.

All 17 tests pass. ruff clean.

## What was NOT verified

- Live end-to-end run on ICANH archive (manager gate).
- LLM per-page fan-out path: `_llm_multipage` is only set when `requested_page_index is None`
  (line 1797), so per-page LLM fan-out already takes the single-page branch — same guard applies.
- `transcribe_review` uses `process_vision` → fix applies automatically.

## What the shell already had (no rebuild needed — iterate)
- iOS entry: `FicheroApp_iOS.swift` → pairs with Mac (QR) → `adoptPairedRemoteLibrary()`
  creates ONE remote `LibraryReference` (the paired path) → `FicheroSharedPlatformRoot`
  → `LibraryWorkspaceRoot(library:)` → `DocumentTabView` → `ContentView` (NavigationSplitView).
- Registry plumbing already exists: `KnownLibraryRegistryStore.shared` reads `/registry`
  and is refreshed on connect. It just had no iOS UI.
- Switching the whole app to another library = set `LibraryManager.currentLibraryId`;
  `LibraryWorkspaceSelection.activeLibrary` re-roots the workspace, `.task(id:)` syncs
  `windowState.libraryId`. (Same mechanism Mac uses.)
- Compact adaptivity already in place: `ContentView.shouldUseSplittablePane` is false on
  compact (#2333 — SplittablePane is desktop/regular-width only), inspector becomes a
  detented `.sheet` on compact (`InspectorPlacement.adaptiveDefault`), and
  `availablePreviewModes` drops `.widescreen` on compact so a phone never renders the
  fixed multi-pane HSplit. NavigationSplitView collapses to a stack natively.

## What I changed
### Chunk 1 — Multiple libraries on iOS (#2394)
- `LibraryManager+Operations.swift`: added `switchToRemoteLibrary(path:displayName:)` —
  iOS-safe switch that reuses an already-open library at that path or creates a remote
  `LibraryReference` (no security scope, no local file-exists check), inserts it after
  Global, sets `currentLibraryId`, and schedules a load. Mirrors `adoptPairedRemoteLibrary`
  but for an arbitrary registry path with a fresh UUID.
- NEW `fichero/Views/Library/iOSLibraryPickerMenu.swift` — a Menu listing the known-library
  registry (+ the active library), with a checkmark on the current one; tap switches via
  `switchToRemoteLibrary`. Refreshes the registry on appear.
- `LibraryWorkspaceRoot.swift` (iOS branch): surfaced the picker as a `.topBarLeading`
  toolbar Menu so it's the first thing reachable on every iOS screen — the "library list".

### Chunk 2 — Compact stack/swipe nav (#2329 / #2334 / #2100)
- `ContentView`: added `preferredCompactColumn` policy + binding on the NavigationSplitView
  so compact reliably lands on the content/detail column (the document list → reader) and
  the sidebar (folder tree + library picker) stays one swipe away. Pure additive arg to the
  existing split view — no new modifier in the type-check-sensitive chain.

## Needs an Xcode build to confirm (I did NOT run xcodebuild — per brief)
- New file `iOSLibraryPickerMenu.swift` must be registered: `ruby scripts/add-swift-file.rb
  fichero/fichero/Views/Library/iOSLibraryPickerMenu.swift` (done by me; manager re-verify).
- Verify the `.topBarLeading` Menu renders in the iOS nav bar alongside the existing
  Capture-Queue toolbar item.
- Verify `NavigationSplitView(columnVisibility:preferredCompactColumn:sidebar:detail:)`
  compiles against the current min-26 SDK.

## Mac-regression risk
- `switchToRemoteLibrary` is cross-platform but only called from the iOS picker.
- `preferredCompactColumn` is inert on macOS (split view never collapses); the binding just
  rides along. Policy returns `.detail` only for compact, `.automatic`-equivalent otherwise.
- No changes to SplittablePane, the Mac sidebar, or the desktop reading workspace.

## New files (manager: register with add-swift-file.rb)
- fichero/fichero/Views/Library/iOSLibraryPickerMenu.swift
