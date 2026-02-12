import SwiftUI

// MARK: - ContentView View Builders Extension
// Agent: ViewBuilderAgent
// Responsibility: Complex view builders for sidebar, content, preview, inspector

extension ContentView {
    
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
        .navigationSplitViewColumnWidth(min: 250, ideal: sidebarWidth, max: 350)
        .focusedSceneValue(\.sidebarMode, $sidebarMode)
    }
    
    // MARK: - Center Content (with Layout Modes)
    
    @ViewBuilder
    var centerContent: some View {
        switch currentLayoutMode {
        case .none:
            // None: Just content, no preview
            contentView
                .navigationSplitViewColumnWidth(min: 350, ideal: 600, max: .infinity)

        case .standard:
            // Standard: Content stacked above preview (vertical split)
            VSplitView {
                contentView
                    .frame(minHeight: 150, idealHeight: 180)

                previewView
                    .frame(minHeight: 400, idealHeight: 720)
            }
            .navigationSplitViewColumnWidth(min: 350, ideal: 700, max: .infinity)

        case .widescreen:
            // Widescreen: Content and preview side-by-side (horizontal split)
            HSplitView {
                contentView
                    .frame(minWidth: 200, idealWidth: 200)

                previewView
                    .frame(minWidth: 400, idealWidth: 800)
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
                .navigationSplitViewColumnWidth(250)
                .frame(width: 250)

        case .chat, .comparison:
            ChatInspector(selectedDocuments: $chatSelectedDocuments)
                .navigationSplitViewColumnWidth(250)
                .frame(width: 250)

        case .workflow:
            WorkflowInspector(
                workflow: $editingWorkflow,
                onAddNode: { tool, position in
                    addNodeFromTool(tool, at: position)
                }
            )
            .navigationSplitViewColumnWidth(250)
            .frame(width: 250)

        case .chain:
            WorkflowInspector(
                workflow: $editingWorkflow,
                onAddNode: { tool, position in
                    addNodeFromTool(tool, at: position)
                }
            )
            .navigationSplitViewColumnWidth(250)
            .frame(width: 250)

        case .batches, .batch, .automation, .schedule, .trigger, .activity:
            EmptyView()
                .navigationSplitViewColumnWidth(0)
        }
    }
    
    // MARK: - Detail View (Right Column)
    
    @ViewBuilder
    var detailView: some View {
        inspectorView
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
