import SwiftUI

// MARK: - ContentView View Builders Extension
// Agent: ViewBuilderAgent
// Responsibility: Complex view builders for sidebar, content, preview, inspector

extension ContentView {

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
            onCreateChatWithDocuments: { documentIds in
                chatSelectedDocuments = Set(documentIds)
            }
        )
        .environmentObject(savedSearchService)
        .environmentObject(conversationService)
        .environmentObject(ErrorService.shared)
        .environmentObject(performanceService)
        .focusable()
        .focused($focusedPane, equals: .sidebar)
        .focusEffectDisabled()
        .overlay { paneFocusIndicator(for: .sidebar) }
        .navigationSplitViewColumnWidth(min: 250, ideal: sidebarWidth, max: 350)
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
        switch currentLayoutMode {
        case .none:
            // None: Just content, no preview
            contentWithOptionalModeRail
                .overlay { paneFocusIndicator(for: .content) }
                .focusable()
                .focused($focusedPane, equals: .content)
                .focusEffectDisabled()
                .navigationSplitViewColumnWidth(min: 350, ideal: 600, max: .infinity)

        case .standard:
            // Standard: Content stacked above preview (vertical split)
            VSplitView {
                contentWithOptionalModeRail
                    .overlay { paneFocusIndicator(for: .content) }
                    .frame(minHeight: 150, idealHeight: 180)
                    .focusable()
                    .focused($focusedPane, equals: .content)
                    .focusEffectDisabled()

                previewView
                    .overlay { paneFocusIndicator(for: .preview) }
                    .frame(minHeight: 400, idealHeight: 720)
                    .focusable()
                    .focused($focusedPane, equals: .preview)
                    .focusEffectDisabled()
            }
            .navigationSplitViewColumnWidth(min: 350, ideal: 700, max: .infinity)

        case .widescreen:
            // Widescreen: Content and preview side-by-side (horizontal split)
            HSplitView {
                contentWithOptionalModeRail
                    .overlay { paneFocusIndicator(for: .content) }
                    .frame(minWidth: 200, idealWidth: 200)
                    .focusable()
                    .focused($focusedPane, equals: .content)
                    .focusEffectDisabled()

                previewView
                    .overlay { paneFocusIndicator(for: .preview) }
                    .frame(minWidth: 400, idealWidth: 800)
                    .focusable()
                    .focused($focusedPane, equals: .preview)
                    .focusEffectDisabled()
            }
            .navigationSplitViewColumnWidth(min: 600, ideal: 1000, max: .infinity)
        }
    }

    // MARK: - Preview View

    /// Preview/editor view for selected item
    @ViewBuilder
    var previewView: some View {
        switch viewMode {
        case .library, .search:
            EditorView(document: detailDocument)

        case .chat, .comparison:
            EmptyView()

        case .workflow, .chain:
            EmptyView()

        case .batches, .batch, .automation, .schedule, .trigger, .activity:
            EmptyView()
        }
    }

    // MARK: - Inspector View

    /// Inspector/info sidebar view (right column - fixed width)
    @ViewBuilder
    var inspectorView: some View {
        switch viewMode {
        case .library, .search:
            DocumentInspector(document: inspectorDocument)
                .navigationSplitViewColumnWidth(
                    min: ContentView.inspectorMinWidth,
                    ideal: inspectorWidth,
                    max: ContentView.inspectorMaxWidth
                )

        case .chat, .comparison:
            ChatInspector(selectedDocuments: $chatSelectedDocuments)
                .navigationSplitViewColumnWidth(
                    min: ContentView.inspectorMinWidth,
                    ideal: inspectorWidth,
                    max: ContentView.inspectorMaxWidth
                )

        case .workflow:
            WorkflowInspector(
                workflow: $editingWorkflow,
                onAddNode: { tool, position in
                    addNodeFromTool(tool, at: position)
                }
            )
            .navigationSplitViewColumnWidth(
                min: ContentView.inspectorMinWidth,
                ideal: inspectorWidth,
                max: ContentView.inspectorMaxWidth
            )

        case .chain:
            WorkflowInspector(
                workflow: $editingWorkflow,
                onAddNode: { tool, position in
                    addNodeFromTool(tool, at: position)
                }
            )
            .navigationSplitViewColumnWidth(
                min: ContentView.inspectorMinWidth,
                ideal: inspectorWidth,
                max: ContentView.inspectorMaxWidth
            )

        case .batches, .batch, .automation, .schedule, .trigger, .activity:
            EmptyView()
                .navigationSplitViewColumnWidth(0)
        }
    }

    // MARK: - Detail View (Right Column)

    @ViewBuilder
    var detailView: some View {
        inspectorView
            .focusable()
            .focused($focusedPane, equals: .inspector)
            .focusEffectDisabled()
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
