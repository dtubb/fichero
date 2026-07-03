
## #2804 — accessibility labels for icon-only buttons — TOOLBAR + SIDEBAR passes done (stopped here)
2026-07-03, f_fichero_claude_swiftui. Bounded per-area commits, each macOS build-gated (isolated xcodebuild, scratch DD, no signing). Approach: add .accessibilityLabel using the existing .help() text; do NOT relabel controls that already carry a text Label or decorative status icons.

### Toolbars — DONE (commit 0f7b7033)
- MiniToolbarComponents generic actions (the called-out :173-176), MiniToolbar split toggles, WorkflowToolbar (import/export/preview/run-on-docs/compare/run), ReaderToolbar (close, page prev/next, zoom in/out, fit, actual-size, magnifier, loupe toggle/lock, edit, annotation tools, pin, more-tools overflow).
- SKIPPED (already labeled/decorative): ChatViewToolbar model menu (shows model name), Label-based menu items, SearchViewToolbar error triangle (decorative), MainToolbar (already had its label).
- NOTE: "reader controls" from the issue = ReaderToolbar → covered in this toolbars pass.

### Sidebar — DONE (commit 69f0c943)
- SidebarViewExtensions bottom action bar (New Item, Remove, Export, Import Files, New Workflow menus/buttons) + SidebarView+ViewComponents filter clear button.
- SKIPPED: PinnedNavigationRows (Label-based: Chat with Docs etc.), filter magnifying-glass (decorative).

### Inspector — DONE (commit b9244510)
- DocumentInspector tab-picker buttons (tab.rawValue), ArtifactListView "Reviewed" seal, DocumentInspectorArtifactsTab+KGSection (filter kinds, text digest, list view, reload — 4), DocumentInspectorArtifactsTab+EntitiesTab (reload, filter kinds — 2).
- SKIPPED (already Label-based/decorative): ArtifactsInspectorPane pin Toggle, CitationsInspectorPane / AnnotationsInspectorPane "Open in Window" toggles, FocusedDocument back button — all use Label(_, systemImage:).

### Reader — DONE (commit <this>)
- ImageViewerComponents iOS (#elseif canImport(UIKit)) in-content controls: Zoom Out, Zoom In, Fit to Window, Actual Size, folder Previous/Next image.
- SKIPPED: View/Close Full Screen (already had labels); macOS reader controls covered by ReaderToolbar in the toolbars pass; AnnotationToolbar (all Label-based); PDFPageWithToolbar/PageContentPane (no icon-only .help buttons).
- NOTE: reader edits sit in the iOS-only branch, so the macOS build doesn't compile them — file still compiles as a whole for macOS; manager's iOS build gate exercises the branch.

macOS build green for all four passes (only the environmental Embed Fichero Engine script phase fails, no swiftc errors); a11y is cross-platform so it also benefits iOS VoiceOver. NOT pushed.

## #2838 — chat route error propagation — 2026-07-03, f_fichero_codex_docs
Removed the `/api/chat` fake-success apology fallback so provider/LLM failures now propagate instead of returning a misleading 200; flipped the former strict-`xfail` repro in `test_routes_chat.py` to a passing prefer-raise assertion. Targeted gate: `PYTHONPATH=fichero-engine/src /Users/danieltubb/code/fichero/.venv/bin/pytest fichero-engine/tests/unit/test_routes_chat.py -q` → `24 passed`.
