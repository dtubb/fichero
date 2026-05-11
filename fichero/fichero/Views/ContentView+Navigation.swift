import SwiftUI

// MARK: - ContentView Content Routing Extension
// Agent: NavigationAgent
// Responsibility: Main content view routing based on AppViewMode

extension ContentView {

    private var libraryLoadErrorMessage: String? {
        guard !documentStore.isLoading else { return nil }
        guard selectedDocuments.isEmpty else { return nil }

        if let error = documentStore.error {
            return error.localizedDescription
        }

        if !documentStore.isConnected {
            return "Cannot connect to the local API server."
        }

        return nil
    }

    // MARK: - Content View Router (Middle Column)

    @ViewBuilder
    var contentView: some View {
        switch viewMode {
        case .library:
            LibraryView(
                documents: selectedDocuments,
                isLoading: documentStore.isLoading,
                isConnected: documentStore.isConnected,
                errorMessage: documentStore.error?.localizedDescription,
                onRetry: {
                    Task { @MainActor in
                        await documentStore.refresh()
                    }
                },
                selection: $browserSelection,
                detailDocument: $detailDocument,
                viewMode: $viewSettings.libraryLayout,
                displayMode: viewDisplayMode,
                folderId: selectedSidebarItemId,
                onRequestFocus: { focusedPane = .content },
                onRequestPreviousPaneFocus: { cyclePaneFocus(reverse: true) },
                onRequestNextPaneFocus: { cyclePaneFocus(reverse: false) },
                onNavigateInto: { doc in navigateToDocument(doc) },
                sidebarHidden: !showSidebar,
                onToolbarSearchSubmit: { query in
                    runToolbarSearch(query)
                }
            )

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
            HStack(spacing: 0) {
                WorkflowListView(
                    displayMode: .list,
                    onOpenWorkflow: { item in viewMode = .workflow(item) }
                )
                .frame(minWidth: 200, maxWidth: 280)

                Divider()

                if let selectedWorkflow = workflow {
                    WorkflowEditor(
                        workflow: selectedWorkflow,
                        editingWorkflow: $editingWorkflow,
                        displayMode: .icon,
                        selectedDocumentIds: Array(browserSelection)
                    )
                    .frame(maxWidth: .infinity)
                } else {
                    ContentUnavailableView(
                        "Select a Workflow",
                        systemImage: "flowchart",
                        description: Text("Choose a workflow from the list to edit")
                    )
                    .frame(maxWidth: .infinity)
                }
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
                "Activity",
                systemImage: "clock",
                description: Text("Batch monitoring is now unified under Activity")
            )

        case .batch:
            ContentUnavailableView(
                "Activity",
                systemImage: "clock",
                description: Text("Batch monitoring is now unified under Activity")
            )

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
            HStack(spacing: 0) {
                ActivityBrowserView(
                    selectedRunId: selectedRun?.id,
                    onSelectRun: { run in viewMode = .activity(run) }
                )
                .frame(minWidth: 200, maxWidth: 280)

                Divider()

                if let run = selectedRun {
                    ActivityDetailView(selectedRun: run)
                        .frame(maxWidth: .infinity)
                } else {
                    ContentUnavailableView(
                        "Select a Run",
                        systemImage: "clock",
                        description: Text("Choose a workflow run from the list")
                    )
                    .frame(maxWidth: .infinity)
                }
            }

        case .ontology:
            // Knowledge Graph entity browser (#498). The OntologyBrowser
            // View exists at Views/KnowledgeGraph/OntologyBrowser/ but
            // its files are not yet in the Xcode project target — added
            // in a follow-up commit that wires the full pbxproj
            // membership for the KG view layer.
            ContentUnavailableView(
                "Knowledge Graph",
                systemImage: "circle.hexagongrid",
                description: Text("Loading entity browser…")
            )
        }
    }
}
