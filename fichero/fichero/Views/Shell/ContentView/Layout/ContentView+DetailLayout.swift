import SwiftUI

// MARK: - ContentView Detail Layout Extension
// Agent: ViewBuilderAgent
// Responsibility: Detail-column chrome (tab strip/status/location bars), the
// widescreen canvas/reading panes, and the preview/inspector/detail views.
// Split out of ContentView+ViewBuilders.swift to keep each file under the
// file_length limit.

extension ContentView {
    @ViewBuilder
    var detailShellColumn: some View {
        VStack(spacing: 0) {
            // Xcode-style detail chrome (tab strip + location/status path bars)
            // is a regular-width affordance. At compact width (iPhone) it wastes
            // the tiny screen and doesn't fit, so it's hidden — the reader gets
            // the full height (#2811). macOS reports a regular/nil size class, so
            // the chrome always renders there.
            // The detail tab strip is RETIRED (Daniel, 2026-08-23): the
            // selected item reads from the top dynamic island, and "open in
            // new tab" returns on the real tab bar when that exists. Panes
            // carry their own PaneHead — no second chrome row above them.
            centerContent
            // NO window-wide status bar any more (Daniel #106-108,
            // 2026-08-09: "we want the status bar just on the library") —
            // the Finder-style path + status rows live in LibraryView's
            // bottom inset, scoped to that pane. See LibraryPathStatusBar.
        }
        .background(Color(platformColor: .textBackgroundColor))
        // Keep every library/preview/reader combination inside the detail
        // column bounds. Without this outer clip, inner split panes can still
        // paint under the shell sidebar or past the left window edge (#3336).
        .clipped()
        // Window split commands + workspace capture (Daniel, 2026-08-29).
        .environment(\.paneSplitCoordinator, paneSplitCoordinator)
    }

    // detailStatusPathBar is RETIRED (Daniel #106-108) — see the comment at
    // its old mount above. selectionStatusText remains in StateDisplay for
    // the toolbar/other readers.

    /// The document-canvas pane of the widescreen reading layout — a PDF page
    /// viewer when a PDF is active, otherwise the image/preview editor. Carries
    /// its own flexible width so it fills whatever the list/reading panes leave.
    /// Extracted so the canvas can be conditionally shown/hidden (#1448).
    @ViewBuilder
    func widescreenCanvasPane(splitKey: String = "canvas") -> some View {
        // Splittable (h/v) image / canvas viewer — #2276. The split key is
        // SLOT-scoped (2026-08-24): two slots hosting previews shared the
        // per-window "canvas" @SceneStorage, so splitting one split both.
        adaptiveSplittablePane(storageKey: splitKey) {
            // The head, the chrome seam, and their sync live in
            // ContentView+PreviewPaneHead.swift (2026-08-29 restructure).
            previewHeadPlumbing(around: widescreenCanvasPaneContent)
        }
    }

    @ViewBuilder
    private var widescreenCanvasPaneContent: some View {
        let stackDocuments = previewStackDocuments(
            selection: browserSelection, in: selectedDocuments
        )
        // Pinned: frozen on the captured document, whatever the selection
        // does (Daniel, 2026-08-23: pin = pin to current view).
        if let pinned = pinnedPreviewDocument {
            EditorView(
                document: pinned,
                showHeader: false,
                onPDFPageIndexChange: { _ in },
                onNavigateToDocument: { _ in },
                selectedDocumentIDs: []
            )
            .frame(maxWidth: .infinity)
            .simultaneousGesture(TapGesture().onEnded { _ in focusedPane = .preview; paneFocusHint = .preview })
        // Finder's stacked multi-selection preview (#95) — same gate as the
        // standard-layout preview pane.
        } else if stackDocuments.count > 1 {
            MultiSelectionPreviewStack(
                documents: stackDocuments,
                frontDocumentId: detailDocument?.id
            )
                .simultaneousGesture(TapGesture().onEnded { _ in focusedPane = .preview; paneFocusHint = .preview })
                .frame(maxWidth: .infinity)
        } else if let pdfDocumentId = detailPDFDocumentId, previewLens == .preview {
            PDFPageWithToolbar(
                documentId: pdfDocumentId,
                pageIndex: selectedPageIndex,
                onPageIndexChange: { index in
                    guard documentScrollSync.beginDriving(.pdf) else { return }
                    syncGridSelectionToPDFPage(index: index)
                },
                documentTitle: detailDocument?.name,
                onClose: { setPaneVisible(.canvas, false) },
                // Geometry lives on the PAGE child, not the parent PDF this
                // pane renders from (#4418 follow-up).
                geometryDocumentId: pageGeometryDocumentId
            )
            .frame(minWidth: ContentView.pdfCanvasMinWidth, maxWidth: .infinity)
            .simultaneousGesture(TapGesture().onEnded { _ in focusedPane = .preview; paneFocusHint = .preview })
        } else {
            let canvasDocument = CanvasDocumentPolicy.documentForCanvas(
                selectedDocumentIds: browserSelection,
                documents: selectedDocuments,
                detailDocument: detailDocument,
                inspectorDocument: inspectorDocument
            )
            EditorView(
                document: canvasDocument,
                showHeader: false,
                onPDFPageIndexChange: { index in
                    syncGridSelectionToPDFPage(index: index)
                },
                onNavigateToDocument: { docId in
                    selectDocument(withId: docId)
                },
                selectedDocumentIDs: browserSelection
            )
            .frame(maxWidth: .infinity)
            .simultaneousGesture(TapGesture().onEnded { _ in focusedPane = .preview; paneFocusHint = .preview })
        }
    }

    /// The reading / WebKit "Knowledge" pane of the widescreen layout.
    /// Extracted so it can be conditionally shown/hidden per-window (#1448).
    @ViewBuilder
    func widescreenReadingPane(splitKey: String = "reading") -> some View {
        widescreenReadingPaneBody(readingSplitKey: splitKey)
    }

    /// What the Reader shows: the selected document, or — when nothing is
    /// selected — the FOLDER that is open.
    ///
    /// With no selection the Reader used to show nothing at all (Daniel,
    /// 2026-08-28: "if only one item is selected it should show the entire
    /// folder, or no items as well; right now it shows nothing"). The engine
    /// already assembles every child page's content into one transcript for a
    /// container, which is exactly what a folder-level read wants, so the
    /// fallback costs no new backend work. It also makes the head's artifact
    /// lens reachable for the folder — a folder-level translation is
    /// selectable the same way a page's is.
    var readerDocument: Document? {
        if let detailDocument { return detailDocument }
        if case .library(let folder) = viewMode { return folder }
        return nil
    }

    @ViewBuilder
    private func widescreenReadingPaneBody(readingSplitKey: String) -> some View {
        // Compute the page count ONCE (#3866): reading `pdfDocPages` twice here
        // (isEmpty + count) recomputed a filter+sort per read — 2x O(n log n) per
        // render. The pane needs only the count, so use the sort-free accessor.
        let pageCount = pdfDocPageCount
        // Multi-selection is stated honestly (Daniel 2026-08-11: three items
        // selected, the preview showed the 3-item stack, the inspector said
        // "3 Items Selected" — and the reader silently showed ONE page's
        // transcript). Same gate as both of those panes. Rendering content
        // for ALL selected items is the pane-rebuild enhancement; until then
        // the reader must not present one item's text as the selection's.
        let readerStack = previewStackDocuments(
            selection: browserSelection, in: selectedDocuments
        )
        // Each SplittablePane instance renders ReadingPaneView independently,
        // giving left and right split panes their own @State (including pin).
        //
        // AnyView — LOAD-BEARING (#4331 family, Daniel's crash 2026-08-11
        // evening): EXC_BAD_ACCESS in objc_retain while initializeWithCopy
        // COPIED the composed reading-pane value through three
        // ExclusiveGesture wrappers (SidebarLayout:242). The multi-select
        // _ConditionalContent grew the value past what the copy machinery
        // survives; erasure at the case boundary caps it, same as the root
        // layout and window root.
        adaptiveSplittablePane(storageKey: readingSplitKey) {
            // ONE pane for both selection widths (2026-08-25): the multi view
            // used to replace ReadingPaneView wholesale, so a 3-item
            // selection erased the head, lens selector and crumbs. Now the
            // Page lens renders the multi list INSIDE the pane's chrome.
            // AnyView stays load-bearing (#4331).
            AnyView(ReadingPaneView(
                liveDocument: readerDocument,
                // NOT gated on the PDF canvas (Daniel, 2026-09-04): an image
                // page never uses that canvas, so the reader was handed no
                // active page and never scrolled to a search hit.
                liveActivePageNumber: readerActivePageNumber,
                livePageCount: pageCount == 0 ? nil : pageCount,
                scrollSync: documentScrollSync,
                onPageSelected: { index in syncGridSelectionToPDFPage(index: index) },
                onClose: { setPaneVisible(.reading, false) },
                multiDocuments: readerStack,
                // The active library-search terms, so the reader lights up
                // where the selected result matched (Daniel, 2026-09-01).
                searchHighlightQuery: chromeUX.readerFindQuery
            ))
        }
        // Native focus rings OFF in this pane: macOS 14+ makes scroll views
        // keyboard-focusable and rings them natively, which painted a
        // persistent blue edge above the reader toolbar. Panes draw no focus
        // ring of their own either (ruling 2026-08-31).
        .focusEffectDisabled()
        .simultaneousGesture(TapGesture().onEnded { _ in focusedPane = .reading; paneFocusHint = .reading })
    }

    // `adaptiveSplittablePane` is internal (not private) because it is also
    // called from ContentView+SidebarLayout.swift's `centerContentRouting`
    // (the widescreen library-pane split) — `private` is file-scoped.
    @ViewBuilder
    func adaptiveSplittablePane<Content: View>(
        storageKey: String,
        @ViewBuilder content: @escaping () -> Content
    ) -> some View {
        if shouldUseSplittablePane {
            SplittablePane(storageKey: storageKey) {
                content()
            }
        } else {
            content()
        }
    }

    // MARK: - Preview View

    /// Preview/editor view for selected item
    @ViewBuilder
    var previewView: some View {
        switch viewMode {
        case .library:
            // Stable .id so EditorView keeps its mount across the
            // first detailDocument nil → some-doc transition. Without
            // a fixed id, SwiftUI's structural-identity pass treats
            // the EditorView differently when its document arg flips,
            // causing the LazyVGrid sibling to re-layout / first-click
            // flash (#788).
            VStack(spacing: 0) {
                let previewDocument = CanvasDocumentPolicy.documentForCanvas(
                    selectedDocumentIds: browserSelection,
                    documents: selectedDocuments,
                    detailDocument: detailDocument,
                    inspectorDocument: inspectorDocument
                )
                let stackDocuments = previewStackDocuments(
                    selection: browserSelection, in: selectedDocuments
                )
                if stackDocuments.count > 1 {
                    // Finder's stacked multi-selection preview (#95): the fan
                    // + count, not a silent preview of only the primary.
                    MultiSelectionPreviewStack(
                        documents: stackDocuments,
                        frontDocumentId: detailDocument?.id
                    )
                } else if let pdfDocumentId = detailPDFDocumentId, previewLens == .preview {
                    PDFReadingView(
                        document: pageFocusDocument ?? detailDocument,
                        pdfDocumentId: pdfDocumentId,
                        pageIndex: selectedPageIndex,
                        contentWidth: $pageContentPaneWidth,
                        onPageIndexChange: { index in
                            guard documentScrollSync.beginDriving(.pdf) else { return }
                            syncGridSelectionToPDFPage(index: index)
                        }
                    )
                    .id("reader.pdf")
                    .background(
                        // Two/three-finger trackpad swipe → previous/next sibling
                        // (#593). Lives behind the reader so it sees the swipe
                        // without intercepting clicks/scrolls.
                        SwipeSiblingNavigator(
                            onNavigatePrevious: navigateSiblingPrevious,
                            onNavigateNext: navigateSiblingNext
                        )
                    )
                } else {
                    EditorView(
                        document: previewDocument,
                        onPDFPageIndexChange: { index in
                            syncGridSelectionToPDFPage(index: index)
                        }
                    )
                    .id("editor.library")
                    .background(
                        // Two/three-finger trackpad swipe → previous/next sibling
                        // (#593). Lives behind the editor so it sees the swipe
                        // without intercepting clicks/scrolls.
                        SwipeSiblingNavigator(
                            onNavigatePrevious: navigateSiblingPrevious,
                            onNavigateNext: navigateSiblingNext
                        )
                    )
                }
            }

        case .chat, .comparison, .workflow, .chain, .batches, .batch,
             .automation, .schedule, .trigger, .activity:
            // #4525 (V3): never a silent EmptyView — the pane stays mounted
            // and says why, from the ONE decided matrix. While the mode's
            // surface still renders in the center takeover (the remaining
            // #4525 step), a `.content` cell here falls back to naming where
            // the surface currently lives rather than showing a blank.
            PaneEmptyStateView(
                reason: PaneContentPlan.plan(for: viewMode).preview.emptyReason
                    ?? "This view is shown in the main area."
            )
        }
    }

    // MARK: - Inspector View

    /// Inspector/info sidebar view (rendered inside .inspector panel)
    @ViewBuilder
    var inspectorView: some View {
        switch viewMode {
        case .library:
            // Multi-selection interim (#146/#147, Daniel: 'this will be
            // tricky for document inspector. perhaps for now it just
            // disables?'): a clear N-items state instead of silently
            // inspecting only the primary. The aggregate views (all entities
            // across the selection; artifacts grouped by source) are the
            // designed follow-up — task #35.
            if browserSelection.count > 1 {
                ContentUnavailableView(
                    "\(browserSelection.count) Items Selected",
                    systemImage: "square.on.square",
                    description: Text(
                        "Select a single item to inspect it. Multi-item editing is coming."
                    )
                )
            } else {
            DocumentInspector(
                document: inspectorDocument,
                onNavigateToSource: { sourceDocId in
                    Task { @MainActor in
                        await navigateToSourcePage(sourceDocId)
                    }
                }
            )
            .environment(documentStore.documentService)
            .environment(artifactService)
            .environment(entityService)
            .environment(kgCurationService)
            .environment(documentStore)
            .environment(artifactStore)
            .environment(entityStore)
            .environment(claimStore)

            }

        case .chat, .comparison:
            ChatInspector(
                selectedDocuments: $chatSelectedDocuments,
                suggestedDocumentIDs: ChatScopeBuilder.currentScopeDocumentIds(
                    browserSelection: browserSelection,
                    currentDocuments: documentStore.currentDocuments,
                    detailDocument: detailDocument
                ),
                onAddSuggestedDocuments: {
                    let scopedIds = ChatScopeBuilder.currentScopeDocumentIds(
                        browserSelection: browserSelection,
                        currentDocuments: documentStore.currentDocuments,
                        detailDocument: detailDocument
                    )
                    chatSelectedDocuments = chatSelectedDocuments.union(scopedIds)
                }
            )

        case .workflow:
            WorkflowInspector(
                workflow: $editingWorkflow,
                onAddNode: { tool, position in
                    addNodeFromTool(tool, at: position)
                }
            )

        case .chain, .batches, .batch, .automation, .schedule, .trigger, .activity:
            // #4525: the honest per-mode empty from the ONE decided matrix,
            // replacing both the generic "Select an item to inspect." stub and
            // the chain's WorkflowInspector bound to whatever workflow was
            // last edited (a stale surface — the pane-audit's 💀 cell).
            PaneEmptyStateView(
                reason: PaneContentPlan.plan(for: viewMode).inspector.emptyReason
                    ?? "Select an item to inspect.",
                systemImage: "info.circle"
            )
        }
    }

    // MARK: - Detail View (Right Column)

    @ViewBuilder
    var detailView: some View {
        inspectorView
            // Focus tracking without .focusable() — avoids swallowing first click
            .simultaneousGesture(TapGesture().onEnded { _ in focusedPane = .inspector; paneFocusHint = .inspector })
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(.bar)
    }
}
