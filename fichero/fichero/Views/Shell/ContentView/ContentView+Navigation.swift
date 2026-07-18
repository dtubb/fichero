import SwiftUI

// MARK: - ContentView Content Routing Extension
// Agent: NavigationAgent
// Responsibility: Main content view routing based on AppViewMode

extension ContentView {

    // MARK: - Content View Router (Middle Column)

    /// Attach targets the chat composer paperclip offers (#2449 step 2): the open
    /// document + the current library view's documents. ChatView has no library
    /// context of its own, so ContentView resolves these from its live state.
    var chatAttachContext: ChatAttachContext {
        let viewDocs = documentStore.currentDocuments
        return ChatAttachContext(
            openDocumentId: detailDocument?.id,
            openDocumentName: detailDocument?.name,
            currentViewLabel: viewDocs.isEmpty ? nil : "Current View (\(viewDocs.count))",
            currentViewDocumentIds: viewDocs.map(\.id)
        )
    }

    @ViewBuilder
    var contentView: some View {
        // #2960: ViewSettings is @Observable via @Environment, which has no
        // projected binding — @Bindable gives `$viewSettings.libraryLayout`.
        @Bindable var viewSettings = viewSettings
        // Knowledge Graph mode intercepts before normal viewMode routing. (#498)
        if sidebarMode == .knowledgeGraph {
            OntologyBrowser()
        } else
        // Research mode intercepts before normal viewMode routing.
        // The project list lives HERE in the content column (a leading rail),
        // NOT in the shell sidebar — the persistent library sidebar stays
        // visible like every other mode (sidebar-persistence fix).
        if sidebarMode == .research {
            if Self.shouldUseCompactNavigationFlow(horizontalSizeClass: horizontalSizeClass) {
                // Compact: project list is the root; selecting a project pushes
                // its workspace, Back returns to the list (#3010).
                compactInnerModeStack(
                    title: "Research",
                    selection: Binding(
                        get: {
                            researchService.projects.first {
                                $0.id == researchService.selectedProjectId
                            }
                        },
                        set: { researchService.selectedProjectId = $0?.id }
                    )
                ) {
                    ResearchProjectListView()
                        .environment(researchService)
                } detail: { project in
                    ResearchWorkspaceView(project: project)
                        .environment(researchService)
                }
            } else {
                HStack(spacing: 0) {
                    ResearchProjectListView()
                        .environment(researchService)
                        .frame(minWidth: 220, maxWidth: 280)

                    Divider()

                    if let project = researchService.projects.first(where: { $0.id == researchService.selectedProjectId })
                        ?? researchService.projects.first {
                        ResearchWorkspaceView(project: project)
                            .environment(researchService)
                            .frame(maxWidth: .infinity)
                    } else {
                        ContentUnavailableView(
                            "No Research Project",
                            systemImage: "flask",
                            description: Text("Create a project in the list to start researching.")
                        )
                        .frame(maxWidth: .infinity)
                    }
                }
            }
        } else {
        switch viewMode {
        case .library:
            // Space (3D) has no renderer yet (#3081) — .space normalizes to an
            // available mode upstream, so the library path renders LibraryView.
            LibraryView(
                documents: selectedDocuments,
                contentCollection: isEntityLibrarySelection ? .entities : .documents,
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
                isPaneFocused: focusedPane == .content,
                displayMode: viewDisplayMode,
                folderId: sidebarSelectionState.selectedItemId,
                onRequestFocus: { focusedPane = .content },
                onRequestPreviousPaneFocus: { cyclePaneFocus(reverse: true) },
                onRequestNextPaneFocus: { cyclePaneFocus(reverse: false) },
                onNavigateInto: { doc in navigateToDocument(doc) },
                onPageFocus: { doc in
                    if pageFocusDocument?.id != doc.id {
                        pageFocusDocument = doc
                    }
                },
                sidebarHidden: !showSidebar,
                onToolbarSearchSubmit: { query in
                    runToolbarSearch(query)
                }
            )
            // Keep the library surface inside the content column across every
            // preview/sidebar layout variant; without this, list/table rows can
            // paint under the shell sidebar or off the left window edge (#3336).
            .clipped()

        case .search(let savedSearch):
            SearchView(
                savedSearch: savedSearch,
                selection: $browserSelection,
                detailDocument: $detailDocument,
                displayMode: $viewDisplayMode,
                // Drive live search from ContentView's SINGLE global toolbar
                // search — SearchView no longer owns its own .searchable (#3163).
                queryText: $toolbarSearchText
            )

        case .chat(let conversation):
            ChatView(
                conversation: conversation,
                selectedDocuments: $chatSelectedDocuments,
                attachContext: chatAttachContext,
                onConversationUpdated: { refreshConversations() }
            )

        case .comparison(let comparison):
            if let comp = comparison {
                ComparisonDetailView(comparisonSummary: comp)
            } else {
                ModelComparisonView()
            }

        case .workflow(let workflow):
            if Self.shouldUseCompactNavigationFlow(horizontalSizeClass: horizontalSizeClass) {
                // Compact: workflow list is the root; selecting a workflow pushes
                // its editor, Back returns to the list (#3010).
                compactInnerModeStack(
                    title: "Workflows",
                    selection: Binding(
                        get: { workflow },
                        set: { viewMode = .workflow($0) }
                    )
                ) {
                    WorkflowListView(
                        displayMode: .list,
                        onOpenWorkflow: { item in viewMode = .workflow(item) }
                    )
                } detail: { selectedWorkflow in
                    WorkflowEditor(
                        workflow: selectedWorkflow,
                        editingWorkflow: $editingWorkflow,
                        displayMode: .icon,
                        selectedDocumentIds: Array(browserSelection)
                    )
                }
            } else {
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
            // Batch-mode GUI (#3536): run a workflow across many folders
            // separately — one run per folder, each tracked in Activity.
            BatchRunView()

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
            if Self.shouldUseCompactNavigationFlow(horizontalSizeClass: horizontalSizeClass) {
                // Compact: run list is the root; selecting a run pushes its detail,
                // Back returns to the list (#3010).
                compactInnerModeStack(
                    title: "Activity",
                    selection: Binding(
                        get: { selectedRun },
                        set: { viewMode = .activity($0) }
                    )
                ) {
                    ActivityBrowserView(
                        selectedRunId: selectedRun?.id,
                        onSelectRun: { run in viewMode = .activity(run) }
                    )
                } detail: { run in
                    ActivityDetailView(selectedRun: run)
                }
            } else {
                ActivityWindowLauncherView(selectedRun: selectedRun)
            }

        }
        }
    }
}
