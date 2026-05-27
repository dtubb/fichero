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
        .focusedSceneValue(\.navigateToParentAction, navigateToParent)
    }

    // MARK: - Center Content (with Layout Modes)

    var showModeRail: Bool {
        // Hide the icons/list/table/map mode strip in KG mode (#895).
        // KG entry lives inside the library sidebar section so
        // sidebarMode stays .library, but the OntologyBrowser has its
        // own MiniToolbar — stacking both bars looks wrong. Workflows
        // doesn't have this problem because sidebarMode flips to
        // .workflows when the user clicks Workflows.
        if case .ontology = viewMode { return false }
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
            }
            // XCUITest hook for the view-mode rail (#1230).
            .accessibilityIdentifier("viewModeRail")
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
        .help("View as: \(mode.rawValue)")
        // Stable per-mode XCUITest hook, e.g. "viewMode-List" (#1230).
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
            // When the active "detail" item is a folder there's nothing to
            // preview — `EditorView` renders `FolderContentsGrid`, which is
            // the same children the main grid is already showing. Force
            // layout to `.none` so the grid takes full width and we don't
            // duplicate the folder's contents in a side/below pane. (#749)
            let layout: LayoutMode = (detailDocument?.docType == .folder)
                ? .none
                : currentLayoutMode
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
                    HStack(spacing: 0) {
                        contentWithOptionalModeRail
                            .overlay { paneFocusIndicator(for: .content) }
                            .frame(width: clampedWidescreenContentPaneWidth)

                        ResizableDivider(
                            width: $widescreenContentPaneWidth,
                            minWidth: ContentView.contentListMinWidth,
                            maxWidth: 900,
                            edge: .leading
                        )

                        if let pdfPath = detailPDFPath {
                            PDFPageWithToolbar(
                                path: pdfPath,
                                pageIndex: selectedPageIndex,
                                onPageIndexChange: { index in
                                    syncGridSelectionToPDFPage(index: index)
                                }
                            )
                            .overlay { paneFocusIndicator(for: .preview) }
                            .frame(maxWidth: .infinity)
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

                        ResizableDivider(
                            width: $pageContentPaneWidth,
                            minWidth: 220,
                            maxWidth: 540,
                            edge: .trailing
                        )

                        knowledgeSurface(
                            for: detailDocument,
                            activePageNumber: detailPDFPath == nil ? nil : selectedPageIndex + 1
                        )
                        .frame(width: CGFloat(pageContentPaneWidth))
                    }
                    .frame(maxWidth: .infinity)
                }
            }
            .animation(.easeInOut(duration: 0.18), value: layout)
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

        case .batches, .batch, .automation, .schedule, .trigger, .activity, .ontology:
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

        case .ontology:
            // Entity inspector placeholder — wired in #1190/#1196
            VStack(alignment: .leading, spacing: 8) {
                Text("Entity Inspector")
                    .font(.headline)
                Text("Select an entity in the Knowledge Graph to see its profile.")
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                Spacer()
            }
            .padding()

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
