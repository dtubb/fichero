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
        // Knowledge Graph mode intercepts before normal viewMode routing. (#498)
        if sidebarMode == .knowledgeGraph {
            OntologyBrowser()
        } else
        // Research mode intercepts before normal viewMode routing.
        if sidebarMode == .research {
            if let project = researchService.projects.first(where: { $0.id == researchService.selectedProjectId })
                ?? researchService.projects.first {
                ResearchWorkspaceView(project: project)
                    .environmentObject(researchService)
            } else {
                ContentUnavailableView(
                    "No Research Project",
                    systemImage: "flask",
                    description: Text("Create a project in the sidebar to start researching.")
                )
            }
        } else {
        switch viewMode {
        case .library:
            if let doc = libraryViewDocument, viewDisplayMode == .realitykit {
                FolderRealityKitSurface(documentId: doc.id, selectedNodeId: .constant(nil))
            } else {
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
                    libraryToolbar: libraryToolbarState,
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
                "Batches",
                systemImage: "square.stack.3d.up",
                description: Text("Batch queue surface is feature-gated and shown independently.")
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

        case .mindPalace:
            // Spatial 3D-2D space. Rooms live in the sidebar (RoomListView);
            // this is the canvas + node inspector. State is shared via
            // MindPalaceState.
            MindPalaceContainer()
        }
        }
    }
}
