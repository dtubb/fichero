import SwiftUI

// MARK: - ContentView Content Routing Extension
// Agent: NavigationAgent
// Responsibility: Main content view routing based on AppViewMode

extension ContentView {

    // MARK: - Content View Router (Middle Column)

    @ViewBuilder
    var contentView: some View {
        switch viewMode {
        case .library:
            VStack(spacing: 0) {
                if !documentStore.isConnected {
                    ConnectionBanner(
                        error: documentStore.error,
                        onRetry: {
                            Task { await documentStore.checkConnection() }
                        }
                    )
                }
                LibraryView(
                    documents: selectedDocuments,
                    selection: $browserSelection,
                    detailDocument: $detailDocument,
                    viewMode: $viewSettings.libraryLayout,
                    displayMode: viewDisplayMode,
                    folderId: selectedSidebarItemId,
                    onRequestFocus: { focusedPane = .content },
                    onRequestPreviousPaneFocus: { cyclePaneFocus(reverse: true) },
                    onRequestNextPaneFocus: { cyclePaneFocus(reverse: false) }
                )
            }

        case .search(let savedSearch):
            SearchView(
                savedSearch: savedSearch,
                selection: $browserSelection,
                detailDocument: $detailDocument,
                displayMode: viewDisplayMode
            )

        case .chat(let conversation):
            ChatView(
                conversation: conversation,
                selectedDocuments: $chatSelectedDocuments,
                onConversationUpdated: { refreshConversations() },
                displayMode: viewDisplayMode
            )

        case .comparison(let comparison):
            if let comp = comparison {
                ComparisonDetailView(comparisonSummary: comp)
            } else {
                ModelComparisonView()
            }

        case .workflow(let workflow):
            if let selectedWorkflow = workflow {
                WorkflowEditor(
                    workflow: selectedWorkflow,
                    editingWorkflow: $editingWorkflow,
                    displayMode: viewDisplayMode
                )
            } else {
                ContentUnavailableView(
                    "Workflows",
                    systemImage: "flowchart",
                    description: Text("Select a workflow or chain from the sidebar to edit")
                )
            }

        case .chain(let chain):
            if let selectedChain = chain {
                ChainEditorView(chain: selectedChain)
            } else {
                ContentUnavailableView(
                    "Create Chain",
                    systemImage: "link.badge.plus",
                    description: Text("Chain creation view")
                )
            }

        case .batches:
            ContentUnavailableView(
                "Batches",
                systemImage: "square.stack.3d.up",
                description: Text("Select a batch in the sidebar to view details")
            )

        case .batch(let batch):
            if let batch = batch {
                BatchDetailView(batch: batch, libraryManager: LibraryManager.shared)
            } else {
                ContentUnavailableView(
                    "Create Batch",
                    systemImage: "square.stack.3d.up.badge.plus",
                    description: Text("Batch creation view coming soon")
                )
            }

        case .automation:
            ContentUnavailableView(
                "Automation",
                systemImage: "timer",
                description: Text("Select a schedule or trigger in the sidebar")
            )

        case .schedule(let schedule):
            if let schedule = schedule {
                ScheduleDetailView(schedule: schedule)
            } else {
                ScheduleEditorView(existingSchedule: nil)
            }

        case .trigger(let trigger):
            if let trigger = trigger {
                TriggerDetailView(trigger: trigger)
            } else {
                TriggerEditorView(existingTrigger: nil)
            }

        case .activity(let selectedRun):
            if let run = selectedRun {
                ActivityDetailView(selectedRun: run)
            } else {
                ContentUnavailableView(
                    "Activity",
                    systemImage: "clock",
                    description: Text("Select a workflow run in the sidebar to view details")
                )
            }
        }
    }
}
