
## #2804 — accessibility labels for icon-only buttons — TOOLBAR + SIDEBAR passes done (stopped here)
2026-07-03, f_fichero_claude_swiftui. Bounded per-area commits, each macOS build-gated (isolated xcodebuild, scratch DD, no signing). Approach: add .accessibilityLabel using the existing .help() text; do NOT relabel controls that already carry a text Label or decorative status icons.

### Toolbars — DONE (commit 0f7b7033)
- MiniToolbarComponents generic actions (the called-out :173-176), MiniToolbar split toggles, WorkflowToolbar (import/export/preview/run-on-docs/compare/run), ReaderToolbar (close, page prev/next, zoom in/out, fit, actual-size, magnifier, loupe toggle/lock, edit, annotation tools, pin, more-tools overflow).
- SKIPPED (already labeled/decorative): ChatViewToolbar model menu (shows model name), Label-based menu items, SearchViewToolbar error triangle (decorative), MainToolbar (already had its label).
- NOTE: "reader controls" from the issue = ReaderToolbar → covered in this toolbars pass.

### Sidebar — DONE (commit 69f0c943)
- SidebarViewExtensions bottom action bar (New Item, Remove, Export, Import Files, New Workflow menus/buttons) + SidebarView+ViewComponents filter clear button.
- SKIPPED: PinnedNavigationRows (Label-based: Chat with Docs etc.), filter magnifying-glass (decorative).

### STOPPED HERE. REMAINING (inspector panes pass — ~15+ icon buttons with .help, no label):
ArtifactListView, ArtifactsInspectorPane, CitationsInspectorPane, AnnotationsInspectorPane, DocumentInspector, DocumentInspectorArtifactsTab+KGSection (4), DocumentInspectorArtifactsTab+EntitiesTab (3), FocusedDocument (detail windows). Same approach (help→accessibilityLabel; skip Label/decorative). Recommend one commit for the inspector pass.

macOS build green for both committed passes; a11y is cross-platform so it also benefits iOS VoiceOver. NOT pushed.
