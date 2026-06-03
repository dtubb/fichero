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
        // min: 180 lets the sidebar collapse tight enough that the mode
        // icons dominate the column with minimal wasted space (#615).
        // Was 250 — felt bloated on small screens.
        .navigationSplitViewColumnWidth(min: 180, ideal: sidebarWidth, max: 360)
        .focusedSceneValue(\.sidebarMode, $sidebarMode)
        // NOTE: \.showInspector is published from the detail column in
        // ContentView.navigationSplitColumn (always present), NOT here — the
        // sidebar leaves the hierarchy when collapsed, which disabled ⌘⌥I
        // and the View-menu toggle while the sidebar was hidden (#1513).
        .focusedSceneValue(\.navigateToParentAction, navigateToParent)
    }

    // MARK: - Center Content (with Layout Modes)

    var showModeRail: Bool {
        return (sidebarMode == .library || sidebarMode == .search)
            && showViewModePicker
            && availableViewDisplayModes.count > 1
    }

    /// Horizontal mode strip — Xcode-style pill-segmented picker inside a
    /// MiniToolbar wrapper so the bar's height matches the preview and
    /// inspector toolbars across the window. Single rounded-capsule
    /// background hosts all icons; the selected one is filled with the
    /// accent. Daniel asked for this 'tab-like' look explicitly.
    @ViewBuilder
    var horizontalModeStrip: some View {
        if showModeRail {
            // Same button style as the DocumentInspector tab bar (full-height
            // hit area, centered icon, rounded-rect selection highlight),
            // centered as a group — so the list mode rail, knowledge surface,
            // and inspector tabs all read identically. (was capsule pills;
            // Daniel preferred the inspector look, 2026-05-26.)
            MiniToolbar {
                Spacer(minLength: 0)
                ForEach(availableViewDisplayModes) { mode in
                    modeRailButton(mode)
                }
                Spacer(minLength: 0)
                // Sort + Filter live here — at the Library view's top-right,
                // next to the display-mode buttons — instead of the global
                // window toolbar (#1477).
                librarySortFilterControls
            }
            // XCUITest hook for the view-mode rail (#1230).
            .accessibilityIdentifier("viewModeRail")
        }
    }

    /// Sort menu + inline-filter toggle for the Library mode rail. Library only
    /// (search/workflows don't carry these). Drives the shared LibraryToolbarState
    /// so the controls and the LibraryView stay in sync (#1477).
    @ViewBuilder
    private var librarySortFilterControls: some View {
        if sidebarMode == .library {
            Menu {
                ForEach(LibrarySortField.allCases) { field in
                    Button {
                        libraryToolbarState.sortFieldRaw = field.rawValue
                    } label: {
                        Label(field.rawValue, systemImage: field.icon)
                        if libraryToolbarState.sortField == field {
                            Image(systemName: "checkmark")
                        }
                    }
                }
                Divider()
                Button {
                    libraryToolbarState.sortAscending = true
                } label: {
                    Text("Ascending")
                    if libraryToolbarState.sortAscending { Image(systemName: "checkmark") }
                }
                Button {
                    libraryToolbarState.sortAscending = false
                } label: {
                    Text("Descending")
                    if !libraryToolbarState.sortAscending { Image(systemName: "checkmark") }
                }
            } label: {
                Image(systemName: "arrow.up.arrow.down")
            }
            .menuStyle(.borderlessButton)
            .fixedSize()
            .help("Sort \(libraryToolbarState.sortField.rawValue), \(libraryToolbarState.sortAscending ? "ascending" : "descending")")
            .accessibilityIdentifier("librarySortMenu")

            if featureManager.isLibraryFilterToolbarEnabled {
                Button {
                    libraryToolbarState.showFilterBar.toggle()
                } label: {
                    Image(systemName: "line.3.horizontal.decrease.circle")
                }
                .buttonStyle(.plain)
                .foregroundStyle(libraryToolbarState.showFilterBar ? Color.accentColor : Color.secondary)
                .help("Filter (⌘F)")
                .accessibilityIdentifier("libraryFilterButton")
            }
        }
    }

    /// One mode-rail tab button, styled like the DocumentInspector tab bar.
    /// Extracted from `horizontalModeStrip` because the inline ForEach body
    /// tripped the SwiftUI type-checker's complexity limit.
    @ViewBuilder
    private func modeRailButton(_ mode: ViewDisplayMode) -> some View {
        let isSelected = viewDisplayMode == mode
        Button {
            updateViewDisplayMode(mode)
        } label: {
            Image(systemName: mode.icon)
                .font(.system(size: 16, weight: .regular))
                .frame(width: 40)
                .frame(maxHeight: .infinity)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .background(
            RoundedRectangle(cornerRadius: 6)
                .fill(isSelected ? Color.accentColor.opacity(0.15) : Color.clear)
        )
        .foregroundStyle(isSelected ? Color.accentColor : Color.secondary)
        .help("\(mode.label) view — \(mode.description.lowercased())")
        // Stable per-mode XCUITest hook, e.g. "viewMode-Table" (#1230) — keeps
        // rawValue so the renamed "Column" label doesn't break the test hook.
        .accessibilityIdentifier("viewMode-\(mode.rawValue)")
    }

    @ViewBuilder
    var contentWithOptionalModeRail: some View {
        if showModeRail {
            VStack(spacing: 0) {
                horizontalModeStrip
                Divider()
                contentView
            }
        } else {
            contentView
        }
    }

    @ViewBuilder
    var centerContent: some View {
        // Non-library/search modes (activity, workflows, chat, etc.) never use the
        // preview split — they own the full content area themselves.
        if !showsPreviewPane {
            contentWithOptionalModeRail
                .overlay { paneFocusIndicator(for: .content) }
                .frame(maxWidth: .infinity)
        } else if !showDocumentGrid {
            // Grid hidden (#616): show only the preview/editor at full width.
            previewView
                .overlay { paneFocusIndicator(for: .preview) }
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
                    contentWithOptionalModeRail
                        .overlay { paneFocusIndicator(for: .content) }
                        .frame(maxWidth: .infinity)

                case .standard:
                    VSplitView {
                        contentWithOptionalModeRail
                            .overlay { paneFocusIndicator(for: .content) }
                            .frame(minHeight: 150, idealHeight: 180)

                        previewView
                            .overlay { paneFocusIndicator(for: .preview) }
                            .frame(minHeight: 400, idealHeight: 720)
                    }
                    .frame(maxWidth: .infinity)

                case .widescreen:
                    // Library list is always present; the document canvas and the
                    // reading/WebKit pane are each independently toggleable
                    // per-window (#1448). When the canvas is hidden the reading
                    // pane takes over the freed space so there's never a gap.
                    HStack(spacing: 0) {
                        // When both reading panes are hidden the list takes the
                        // whole width instead of staying a fixed column with a
                        // blank grey area beside it (#1516). list-only is a valid
                        // state — the library list is the always-present spine.
                        contentWithOptionalModeRail
                            .overlay { paneFocusIndicator(for: .content) }
                            .frame(
                                width: (showDocumentCanvas || showReadingPane)
                                    ? clampedWidescreenContentPaneWidth : .infinity
                            )

                        if showDocumentCanvas || showReadingPane {
                            ResizableDivider(
                                width: $widescreenContentPaneWidth,
                                minWidth: ContentView.contentListMinWidth,
                                maxWidth: 900,
                                edge: .leading
                            )
                        }

                        if showDocumentCanvas {
                            widescreenCanvasPane

                            if showReadingPane {
                                ResizableDivider(
                                    width: $pageContentPaneWidth,
                                    minWidth: 220,
                                    maxWidth: 540,
                                    edge: .trailing
                                )
                                widescreenReadingPane
                                    .frame(width: CGFloat(pageContentPaneWidth))
                            }
                        } else if showReadingPane {
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
        if let pdfPath = detailPDFPath {
            PDFPageWithToolbar(
                path: pdfPath,
                pageIndex: selectedPageIndex,
                onPageIndexChange: { index in
                    guard documentScrollSync.beginDriving(.pdf) else { return }
                    syncGridSelectionToPDFPage(index: index)
                }
            )
            .overlay { paneFocusIndicator(for: .preview) }
            .frame(minWidth: ContentView.pdfCanvasMinWidth, maxWidth: .infinity)
        } else {
            EditorView(
                document: detailDocument,
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
        knowledgeSurface(
            for: detailDocument,
            activePageNumber: detailPDFPath == nil ? nil : selectedPageIndex + 1,
            pageCount: pdfDocPages.isEmpty ? nil : pdfDocPages.count,
            scrollSync: documentScrollSync,
            onPageSelected: { index in
                syncGridSelectionToPDFPage(index: index)
            }
        )
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

                EditorView(
                    document: detailDocument,
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

        case .batches, .batch, .automation, .schedule, .trigger, .activity, .mindPalace:
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

        case .batches, .batch, .automation, .schedule, .trigger, .activity, .mindPalace:
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
