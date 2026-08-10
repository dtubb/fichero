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
            if horizontalSizeClass != .compact {
                detailTabStrip
                Divider()
            }
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
    }

    private var detailTabStrip: some View {
        HStack(spacing: 8) {
            Label {
                Text(toolbarTitle)
                    .font(.subheadline)
                    .lineLimit(1)
            } icon: {
                Image(systemName: toolbarIcon)
            }
            .labelStyle(.titleAndIcon)

            Spacer(minLength: 8)

            Button {
                WindowOpener.open(libraryId: windowState.libraryId, asTab: true, using: openWindow)
            } label: {
                Image(systemName: "plus")
            }
            .buttonStyle(.borderless)
            .controlSize(.small)
            .help("Open current library in new tab")
            .accessibilityLabel("Open current library in new tab")
        }
        .padding(.horizontal, 10)
        .frame(height: 32)
        .background(.bar)
    }

    // detailStatusPathBar is RETIRED (Daniel #106-108) — see the comment at
    // its old mount above. selectionStatusText remains in StateDisplay for
    // the toolbar/other readers.

    /// The document-canvas pane of the widescreen reading layout — a PDF page
    /// viewer when a PDF is active, otherwise the image/preview editor. Carries
    /// its own flexible width so it fills whatever the list/reading panes leave.
    /// Extracted so the canvas can be conditionally shown/hidden (#1448).
    @ViewBuilder
    var widescreenCanvasPane: some View {
        // Splittable (h/v) image / canvas viewer — #2276.
        adaptiveSplittablePane(storageKey: "canvas") {
            widescreenCanvasPaneContent
        }
    }

    @ViewBuilder
    private var widescreenCanvasPaneContent: some View {
        let stackDocuments = previewStackDocuments(
            selection: browserSelection, in: documentStore.currentDocuments
        )
        // Finder's stacked multi-selection preview (#95) — same gate as the
        // standard-layout preview pane.
        if stackDocuments.count > 1 {
            MultiSelectionPreviewStack(documents: stackDocuments)
                .overlay { paneFocusIndicator(for: .preview) }
                .simultaneousGesture(TapGesture().onEnded { _ in focusedPane = .preview; paneFocusHint = .preview })
                .frame(maxWidth: .infinity)
        } else if let pdfDocumentId = detailPDFDocumentId {
            PDFPageWithToolbar(
                documentId: pdfDocumentId,
                pageIndex: selectedPageIndex,
                onPageIndexChange: { index in
                    guard documentScrollSync.beginDriving(.pdf) else { return }
                    syncGridSelectionToPDFPage(index: index)
                },
                documentTitle: detailDocument?.name,
                onClose: { setPaneVisible(.canvas, false) }
            )
            .frame(minWidth: ContentView.pdfCanvasMinWidth, maxWidth: .infinity)
            .simultaneousGesture(TapGesture().onEnded { _ in focusedPane = .preview; paneFocusHint = .preview })
            .overlay { paneFocusIndicator(for: .preview) }
        } else {
            let canvasDocument = CanvasDocumentPolicy.documentForCanvas(
                selectedDocumentIds: browserSelection,
                documents: documentStore.currentDocuments,
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
            .overlay { paneFocusIndicator(for: .preview) }
        }
    }

    /// The reading / WebKit "Knowledge" pane of the widescreen layout.
    /// Extracted so it can be conditionally shown/hidden per-window (#1448).
    @ViewBuilder
    var widescreenReadingPane: some View {
        // Compute the page count ONCE (#3866): reading `pdfDocPages` twice here
        // (isEmpty + count) recomputed a filter+sort per read — 2x O(n log n) per
        // render. The pane needs only the count, so use the sort-free accessor.
        let pageCount = pdfDocPageCount
        // Each SplittablePane instance renders ReadingPaneView independently,
        // giving left and right split panes their own @State (including pin).
        adaptiveSplittablePane(storageKey: "reading") {
            ReadingPaneView(
                liveDocument: detailDocument,
                liveActivePageNumber: detailPDFDocumentId == nil ? nil : selectedPageIndex + 1,
                livePageCount: pageCount == 0 ? nil : pageCount,
                scrollSync: documentScrollSync,
                onPageSelected: { index in syncGridSelectionToPDFPage(index: index) },
                onClose: { setPaneVisible(.reading, false) }
            )
        }
        .overlay { paneFocusIndicator(for: .reading) }
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
                    documents: documentStore.currentDocuments,
                    detailDocument: detailDocument,
                    inspectorDocument: inspectorDocument
                )
                let stackDocuments = previewStackDocuments(
                    selection: browserSelection, in: documentStore.currentDocuments
                )
                if stackDocuments.count > 1 {
                    // Finder's stacked multi-selection preview (#95): the fan
                    // + count, not a silent preview of only the primary.
                    MultiSelectionPreviewStack(documents: stackDocuments)
                } else if let pdfDocumentId = detailPDFDocumentId {
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
            .overlay { paneFocusIndicator(for: .inspector) }
            .simultaneousGesture(TapGesture().onEnded { _ in focusedPane = .inspector; paneFocusHint = .inspector })
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(.bar)
    }
}
