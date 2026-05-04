import SwiftUI

// MARK: - ContentView View Builders Extension
// Agent: ViewBuilderAgent
// Responsibility: Complex view builders for sidebar, content, preview, inspector

extension ContentView {
    private var clampedWidescreenContentPaneWidth: CGFloat {
        CGFloat(min(max(widescreenContentPaneWidth, 180), 900))
    }

    /// Inspector only applies for modes that have inspectable content.
    /// Activity, batch, and automation views manage their own detail pane.
    var showInspectorForCurrentMode: Bool {
        switch viewMode {
        case .activity, .batches, .batch, .automation, .schedule, .trigger:
            return false
        default:
            return true
        }
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
    }

    // MARK: - Center Content (with Layout Modes)

    var showVerticalModeRail: Bool {
        (sidebarMode == .library || sidebarMode == .search)
            && showViewModePicker
            && availableViewDisplayModes.count > 1
    }

    @ViewBuilder
    var verticalModeRail: some View {
        if showVerticalModeRail {
            VStack(spacing: 8) {
                ForEach(availableViewDisplayModes) { mode in
                    Button {
                        updateViewDisplayMode(mode)
                    } label: {
                        Image(systemName: mode.icon)
                            .frame(width: 24, height: 24)
                    }
                    .buttonStyle(.plain)
                    .padding(6)
                    .background(
                        RoundedRectangle(cornerRadius: 8)
                            .fill(viewDisplayMode == mode ? Color.accentColor.opacity(0.2) : Color.clear)
                    )
                    .help("View as: \(mode.rawValue)")
                }

                Spacer(minLength: 0)
            }
            .padding(.top, 8)
            .padding(.horizontal, 8)
            .frame(width: 44)
            .background(Color(nsColor: .windowBackgroundColor).opacity(0.35))
        }
    }

    @ViewBuilder
    var contentWithOptionalModeRail: some View {
        if showVerticalModeRail {
            HStack(spacing: 0) {
                verticalModeRail
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
                    // Widescreen: Content and preview side-by-side.
                    // Uses HStack + ResizableDivider so content pane width is stored
                    // and only changes on user drag (HSplitView ignores idealWidth).
                    HStack(spacing: 0) {
                        contentWithOptionalModeRail
                            .overlay { paneFocusIndicator(for: .content) }
                            .frame(width: clampedWidescreenContentPaneWidth)

                        ResizableDivider(
                            width: $widescreenContentPaneWidth,
                            minWidth: 180,
                            maxWidth: 900,
                            edge: .leading
                        )

                        EditorView(
                            document: detailDocument,
                            showHeader: false,
                            onPDFPageIndexChange: { index in
                                syncGridSelectionToPDFPage(index: index)
                            }
                        )
                        .overlay { paneFocusIndicator(for: .preview) }
                        .frame(maxWidth: .infinity)
                    }
                    .frame(maxWidth: .infinity)
                }
            }
            .animation(.easeInOut(duration: 0.18), value: layout)
        }
    }

    /// Sync grid selection to the PDF page at `index`. Fired from
    /// PDFPageView's coordinator when the user scrolls to a different page
    /// in multi-page mode (#586). Finds the matching page Document among
    /// `documentStore.currentDocuments` (populated when the parent PDF was
    /// selected via `selectCollection`) and updates `detailDocument`.
    ///
    /// The `sequence - 1 == index` formula converts our 1-based `sequence`
    /// (page_number) to PDFKit's 0-based index.
    func syncGridSelectionToPDFPage(index: Int) {
        let match = documentStore.currentDocuments.first { doc in
            doc.docType == .page && (doc.sequence ?? 0) == index + 1
        }
        if let match, detailDocument?.id != match.id {
            detailDocument = match
            browserSelection = [match.id]
        }
    }

    // MARK: - Preview View

    /// Preview/editor view for selected item
    @ViewBuilder
    var previewView: some View {
        switch viewMode {
        case .library, .search:
            EditorView(
                document: detailDocument,
                onPDFPageIndexChange: { index in
                    syncGridSelectionToPDFPage(index: index)
                }
            )

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
            DocumentInspector(document: inspectorDocument)

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
                Text("No inspector content for this view.")
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

/// Draggable divider for resizing adjacent panels.
/// - `leadingPanel`: the panel being resized is on the LEFT (drag right to grow)
/// - `trailingPanel`: the panel being resized is on the RIGHT (drag left to grow)
struct ResizableDivider: View {
    @Binding var width: Double
    let minWidth: Double
    let maxWidth: Double
    var edge: Edge = .trailing
    @State private var initialWidth: Double?

    enum Edge {
        case leading   // panel on left — drag right to grow
        case trailing  // panel on right — drag left to grow
    }

    var body: some View {
        // 8px clear hit zone with a 1px visible separator centered inside.
        Color.clear
            .frame(width: 8)
            .overlay(
                Rectangle()
                    .fill(Color(nsColor: .separatorColor))
                    .frame(width: 1)
            )
            .contentShape(Rectangle())
            .onHover { hovering in
                if hovering {
                    NSCursor.resizeLeftRight.set()
                } else {
                    NSCursor.arrow.set()
                }
            }
            .gesture(
                // Use global coordinate space so the delta is stable even when
                // the divider moves during drag (the classic SwiftUI oscillation bug).
                DragGesture(minimumDistance: 1, coordinateSpace: .global)
                    .onChanged { value in
                        if initialWidth == nil { initialWidth = width }
                        guard let start = initialWidth else { return }
                        let delta = value.location.x - value.startLocation.x
                        let newWidth = edge == .trailing
                            ? start - delta
                            : start + delta
                        width = min(max(newWidth, minWidth), maxWidth)
                    }
                    .onEnded { _ in
                        initialWidth = nil
                    }
            )
    }
}

/// A border that briefly shows accent color when focus changes, then fades out
struct FadingFocusBorder: View {
    let isActive: Bool
    @State private var opacity: Double = 0

    var body: some View {
        RoundedRectangle(cornerRadius: 0)
            .strokeBorder(Color.accentColor, lineWidth: 2)
            .opacity(opacity)
            .onChange(of: isActive) { _, active in
                if active {
                    // Show immediately
                    withAnimation(.easeIn(duration: 0.15)) {
                        opacity = 1.0
                    }
                    // Fade out after 2 seconds
                    Task { @MainActor in
                        try? await Task.sleep(for: .seconds(2))
                        withAnimation(.easeOut(duration: 0.8)) {
                            opacity = 0
                        }
                    }
                } else {
                    withAnimation(.easeOut(duration: 0.2)) {
                        opacity = 0
                    }
                }
            }
    }
}
