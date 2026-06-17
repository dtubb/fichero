import SwiftUI

// MARK: - ContentView View Builders Extension
// Agent: ViewBuilderAgent
// Responsibility: Complex view builders for sidebar, content, preview, inspector

extension ContentView {
    private var clampedWidescreenContentPaneWidth: CGFloat {
        CGFloat(min(max(widescreenContentPaneWidth, ContentView.contentListMinWidth), 900))
    }

    var effectiveCenterIdealWidth: Double {
        // .inspector() is now a sibling of NavigationSplitView, not nested inside the detail
        // column. The split view gets whatever width the inspector leaves, so the content
        // ideal is the same whether the inspector is shown or hidden.
        max(contentWidth, 600)
    }

    // MARK: - Pane Focus Indicator

    /// Returns a view that shows an accent-colored border when the given pane has keyboard focus,
    /// then fades out after a brief moment (like Tinderbox's focus highlight).
    func paneFocusIndicator(for pane: PaneFocus) -> some View {
        FadingFocusBorder(isActive: focusedPane == pane)
            .allowsHitTesting(false)
    }

    // MARK: - Sidebar

    @ViewBuilder
    var sidebarContent: some View {
        // #2274: chat surface ABOVE the folder/file sidebar in the LEFT column
        // (reform master plan §6d / §7.10). It reuses the existing ChatView, so
        // send/stream flow through the same ChatServiceGenerated path —
        // no second networking surface. The file tree stays the column's spine.
        VStack(spacing: 0) {
            SidebarChatSurface(selectedDocuments: $chatSelectedDocuments)

            SidebarView(
                sidebarMode: $sidebarMode,
                viewMode: $viewMode,
                selectedItemId: $selectedSidebarItemId,
                libraryManager: LibraryManager.shared,
                itemRegistry: itemRegistry,
                apiClient: apiClient,
                windowPersistenceId: sidebarWindowPersistenceId,
                onCreateChatWithDocuments: { documentIds in
                    chatSelectedDocuments = Set(documentIds)
                },
                onOpenChatWithCurrentScope: {
                    openChatWithCurrentScope()
                }
            )
            .environmentObject(savedSearchService)
            .environmentObject(conversationService)
            .environmentObject(ErrorService.shared)
            .environmentObject(performanceService)
            .overlay { paneFocusIndicator(for: .sidebar) }
            // Make the sidebar focusable so arrow keys navigate the List.
            // (Removing this broke arrow-key navigation — see #560.)
            .focusable()
            .focused($focusedPane, equals: .sidebar)
            .focusEffectDisabled()
        }
        // min: 180 lets the sidebar collapse tight enough that the mode
        // icons dominate the column with minimal wasted space (#615).
        // Was 250 — felt bloated on small screens.
        .navigationSplitViewColumnWidth(min: ContentView.sidebarMinWidth, ideal: sidebarWidth, max: 360)
        .focusedSceneValue(\.sidebarMode, $sidebarMode)
        // NOTE: \.showInspector is published from the detail column in
        // ContentView.navigationSplitColumn (always present), NOT here — the
        // sidebar leaves the hierarchy when collapsed, which disabled ⌘⌥I
        // and the View-menu toggle while the sidebar was hidden (#1513).
        .focusedSceneValue(\.navigateToParentAction, navigateToParent)
    }

    // MARK: - Center Content (with Layout Modes)

    // The library/search view-mode icon rail (`horizontalModeStrip`) that used
    // to sit at the top of the content column was removed (#2032): presentation
    // controls live in the View menu (ViewMenuCommands.LibraryLayoutSection,
    // ⌘1–4), not in a floating in-content icon bar. The mode-switch state is
    // unchanged — the View menu still drives `viewSettings.libraryLayout`.
    @ViewBuilder
    var contentWithOptionalModeRail: some View {
        contentView
    }

    @ViewBuilder
    var centerContent: some View {
        // Non-library/search modes (activity, workflows, chat, etc.) never use the
        // preview split — they own the full content area themselves.
        if !showsPreviewPane {
            contentWithOptionalModeRail
                .overlay { paneFocusIndicator(for: .content) }
                .frame(maxWidth: .infinity)
        } else {
            // Folders now show the current layout so the WebKit/reading
            // pane remains visible for folder-level aggregate content (#1405).
            let layout: LayoutMode = currentLayoutMode
            // Group + .animation gives SwiftUI a stable outer identity so the
            // first .none → .standard/.widescreen transition (when the user
            // first activates a doc from full-grid) animates smoothly instead
            // of remounting + flashing every grid cell. (#770/#778 follow-up)
            Group {
                switch layout {
                case .none:
                    if showDocumentGrid {
                        contentWithOptionalModeRail
                            .overlay { paneFocusIndicator(for: .content) }
                            .frame(maxWidth: .infinity)
                    } else {
                        // Grid hidden (#616): show only the preview/editor at full width.
                        previewView
                            .overlay { paneFocusIndicator(for: .preview) }
                            .frame(maxWidth: .infinity)
                    }

                case .standard:
                    if showDocumentGrid {
                        VSplitView {
                            contentWithOptionalModeRail
                                .overlay { paneFocusIndicator(for: .content) }
                                .frame(minHeight: 150, idealHeight: 180)

                            previewView
                                .overlay { paneFocusIndicator(for: .preview) }
                                .frame(minHeight: 400, idealHeight: 720)
                        }
                        .frame(maxWidth: .infinity)
                    } else {
                        previewView
                            .overlay { paneFocusIndicator(for: .preview) }
                            .frame(maxWidth: .infinity)
                    }

                case .widescreen:
                    // Library/list, document canvas, and reading/WebKit are
                    // independently toggleable per-window (#1448). Hiding the
                    // Library pane must not collapse the reading workspace into
                    // a different single-preview layout.
                    let panePlan = WidescreenPanePlan.make(
                        showDocumentGrid: showDocumentGrid,
                        showDocumentCanvas: showDocumentCanvas,
                        showReadingPane: showReadingPane
                    )
                    HStack(spacing: 0) {
                        if panePlan.showsLibraryPane {
                            // When both reading panes are hidden the list takes the
                            // whole width instead of staying a fixed column with a
                            // blank grey area beside it (#1516). list-only is a valid
                            // state — the library list is the always-present spine.
                            // list-only is full-width. `width: .infinity` is an invalid
                            // frame dimension (SwiftUI logs "Invalid frame dimension
                            // (negative or non-finite)" #2006) — flex with maxWidth
                            // instead, and pin a fixed width only when a reading pane
                            // shares the row.
                            let widescreenContentFixedWidth: CGFloat? =
                                (panePlan.showsCanvasPane || panePlan.showsReadingPane)
                                    ? clampedWidescreenContentPaneWidth : nil
                            // Splittable (h/v) Library list pane — #2276.
                            SplittablePane(storageKey: "library") {
                                contentWithOptionalModeRail
                            }
                            .overlay { paneFocusIndicator(for: .content) }
                            .frame(width: widescreenContentFixedWidth)
                            .frame(maxWidth: widescreenContentFixedWidth == nil ? .infinity : nil)
                        }

                        if panePlan.showsLibraryDivider {
                            ResizableDivider(
                                width: $widescreenContentPaneWidth,
                                minWidth: ContentView.contentListMinWidth,
                                maxWidth: 900,
                                edge: .leading
                            )
                        }

                        if panePlan.showsCanvasPane {
                            widescreenCanvasPane

                            if panePlan.showsCanvasReadingDivider {
                                ResizableDivider(
                                    width: $pageContentPaneWidth,
                                    minWidth: ContentView.readingPaneMinWidth,
                                    maxWidth: 540,
                                    edge: .trailing
                                )
                                widescreenReadingPane
                                    .frame(width: CGFloat(pageContentPaneWidth))
                            }
                        } else if panePlan.showsReadingPane {
                            widescreenReadingPane
                                .frame(maxWidth: .infinity)
                        }
                    }
                    .frame(maxWidth: .infinity)
                }
            }
            .animation(.easeInOut(duration: 0.18), value: layout)
        }
    }

    /// The document-canvas pane of the widescreen reading layout — a PDF page
    /// viewer when a PDF is active, otherwise the image/preview editor. Carries
    /// its own flexible width so it fills whatever the list/reading panes leave.
    /// Extracted so the canvas can be conditionally shown/hidden (#1448).
    @ViewBuilder
    var widescreenCanvasPane: some View {
        // Splittable (h/v) image / canvas viewer — #2276.
        SplittablePane(storageKey: "canvas") {
            widescreenCanvasPaneContent
        }
    }

    @ViewBuilder
    private var widescreenCanvasPaneContent: some View {
        if let pdfDocumentId = detailPDFDocumentId {
            PDFPageWithToolbar(
                documentId: pdfDocumentId,
                pageIndex: selectedPageIndex,
                onPageIndexChange: { index in
                    guard documentScrollSync.beginDriving(.pdf) else { return }
                    syncGridSelectionToPDFPage(index: index)
                }
            )
            .overlay { paneFocusIndicator(for: .preview) }
            .frame(minWidth: ContentView.pdfCanvasMinWidth, maxWidth: .infinity)
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
            .overlay { paneFocusIndicator(for: .preview) }
            .frame(maxWidth: .infinity)
        }
    }

    /// The reading / WebKit "Knowledge" pane of the widescreen layout.
    /// Extracted so it can be conditionally shown/hidden per-window (#1448).
    @ViewBuilder
    var widescreenReadingPane: some View {
        // Splittable (h/v) WebKit/Knowledge reading surface — #2276.
        SplittablePane(storageKey: "reading") {
            knowledgeSurface(
                for: detailDocument,
                activePageNumber: detailPDFDocumentId == nil ? nil : selectedPageIndex + 1,
                pageCount: pdfDocPages.isEmpty ? nil : pdfDocPages.count,
                scrollSync: documentScrollSync,
                onPageSelected: { index in
                    syncGridSelectionToPDFPage(index: index)
                }
            )
        }
    }

    // MARK: - Preview View

    /// Preview/editor view for selected item
    @ViewBuilder
    var previewView: some View {
        switch viewMode {
        case .library, .search:
            // Stable .id so EditorView keeps its mount across the
            // first detailDocument nil → some-doc transition. Without
            // a fixed id, SwiftUI's structural-identity pass treats
            // the EditorView differently when its document arg flips,
            // causing the LazyVGrid sibling to re-layout / first-click
            // flash (#788).
            VStack(spacing: 0) {
                // Top-left × button to hide the preview pane — matches
                // the inspector's close-on-the-corner convention. Daniel:
                // 'we also want a close x in the preview toolbar so that
                // we can hide the preview … in the top left.'
                MiniToolbar {
                    Button {
                        viewSettings.previewMode = .none
                    } label: {
                        Image(systemName: "xmark.circle.fill")
                            .foregroundStyle(.secondary)
                    }
                    .buttonStyle(.plain)
                    .help("Hide preview")
                    Spacer(minLength: 0)
                }

                let previewDocument = CanvasDocumentPolicy.documentForCanvas(
                    selectedDocumentIds: browserSelection,
                    documents: documentStore.currentDocuments,
                    detailDocument: detailDocument,
                    inspectorDocument: inspectorDocument
                )
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

        case .chat, .comparison:
            EmptyView()

        case .workflow, .chain:
            EmptyView()

        case .batches, .batch, .automation, .schedule, .trigger, .activity:
            EmptyView()
        }
    }

    // MARK: - Inspector View

    /// Inspector/info sidebar view (rendered inside .inspector panel)
    @ViewBuilder
    var inspectorView: some View {
        switch viewMode {
        case .library, .search:
            DocumentInspector(
                document: inspectorDocument,
                onNavigateToSource: { sourceDocId in
                    Task { @MainActor in
                        await navigateToSourcePage(sourceDocId)
                    }
                }
            )

        case .chat, .comparison:
            ChatInspector(selectedDocuments: $chatSelectedDocuments)

        case .workflow:
            WorkflowInspector(
                workflow: $editingWorkflow,
                onAddNode: { tool, position in
                    addNodeFromTool(tool, at: position)
                }
            )

        case .chain:
            WorkflowInspector(
                workflow: $editingWorkflow,
                onAddNode: { tool, position in
                    addNodeFromTool(tool, at: position)
                }
            )

        case .batches, .batch, .automation, .schedule, .trigger, .activity:
            VStack(alignment: .leading, spacing: 8) {
                Text("Inspector")
                    .font(.headline)
                Text("Select an item to inspect.")
                    .foregroundStyle(.secondary)
                Spacer()
            }
            .padding()
        }
    }

    // MARK: - Detail View (Right Column)

    @ViewBuilder
    var detailView: some View {
        inspectorView
            // Focus tracking without .focusable() — avoids swallowing first click
            .overlay { paneFocusIndicator(for: .inspector) }
    }

    // MARK: - Breadcrumb

    @ViewBuilder
    func breadcrumbView(for doc: Document) -> some View {
        HStack(spacing: 4) {
            Text(doc.name)
                .fontWeight(.medium)
        }
    }
}
