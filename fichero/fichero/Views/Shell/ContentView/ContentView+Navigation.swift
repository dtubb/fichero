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
            // AnyView is load-bearing (#4331): the fully composed library-case
            // generic, nested inside the shell's getter chain, produced a mangled
            // type whose runtime metadata instantiation recursed past the 1MB
            // iOS main-thread stack (fine on macOS's 8MB) — instant launch crash.
            // Erasing at the case boundary bounds the type depth on every layout.
            AnyView(LibraryView(
                // Transient search (#4106/S2): while a toolbar query is
                // active the library column shows its resolved hits in
                // relevance order; every Library view mode presents them.
                documents: activeSearchQuery == nil ? selectedDocuments : searchResultDocuments,
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
                // The HINT is part of "focused" (2026-08-11, Daniel's Mail
                // comparison): focusedPane is FocusState and stays nil unless
                // a view carries a matching .focused binding — only the
                // sidebar does — so a clicked library row rendered the
                // UNFOCUSED grey+accent selection instead of Mail's
                // accent-bar-with-white. Every pane tap already writes the
                // hint, so hint==.content is "the library is the active pane".
                isPaneFocused: focusedPane == .content || paneFocusHint == .content,
                displayMode: viewDisplayMode,
                folderId: sidebarSelectionState.selectedItemId,
                onRequestFocus: { focusedPane = .content; paneFocusHint = .content },
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
                },
                onAddToChat: {
                    openChatWithCurrentScope()
                },
                // Argument order follows LibraryView's DECLARATION order —
                // Swift requires it for labelled parameters, and these two
                // pairs were added by different changes (#4407 then #4403), so
                // the call site had drifted out of order.
                //
                // #4407: the search field lives in the library's mini toolbar
                // now, so its text and mode are handed to the pane that owns it.
                searchFieldText: $toolbarSearchText,
                searchFieldMode: Binding(
                    get: { SearchFieldMode(rawValue: searchFieldModeRaw) ?? .ask },
                    set: { searchFieldModeRaw = $0.rawValue }
                ),
                // #4521: the field is summoned by the toolbar search toggle;
                // a Binding so in-pane dismissal can flip the same state.
                searchFieldVisible: Binding(
                    get: { showSearchField },
                    set: { setSearchFieldVisible($0) }
                ),
                // #4403: the grid renders only the document leg, so it must be
                // told what the search actually found — otherwise its empty
                // state contradicts the header counting every kind.
                activeSearchQuery: activeSearchQuery,
                searchHitCounts: transientSearchHitCounts
            )
            // #4513: LibraryView reads @Environment(ArtifactService.self), and a
            // missing @Environment object is a FATAL ERROR rather than a nil —
            // the library column trapped on open. ContentView holds the service
            // and the value should inherit, but the AnyView erasure above is a
            // hosting boundary, and #4448 established that this shell re-hosts
            // content outside the inheriting tree at exactly such boundaries.
            //
            // Injected explicitly here for the same reason the activity stores
            // ride an explicit host: inheritance that works today is not a
            // guarantee, and the failure mode is a crash rather than a
            // degradation. Re-injecting a value that was already in scope is a
            // no-op; omitting one is a trap.
            //
            // ALL of them, not a hand-picked one (2026-08-11: the horizontal
            // library split's second pane died on WorkflowExecutionObserver —
            // artifactService alone was exactly the hand-picked-list mistake
            // the inspector boundary comment already warns about). This is the
            // same set inspectorContainerView re-injects.
            .environment(artifactService)
            .environment(windowState)
            .environment(executionObserver)
            .environment(kgFocusState)
            .environment(claimFocusState)
            .environment(viewSettings)
            .environment(appState)
            .environment(errorService)
            .environment(featureManager)
            .environment(libraryManager)
            // Keep the library surface inside the content column across every
            // preview/sidebar layout variant; without this, list/table rows can
            // paint under the shell sidebar or off the left window edge (#3336).
            .clipped()
            // Transient-search chrome (#4106 S2/S9/S5): honest result count,
            // Load More, explicit Save Search, and the engine's error detail —
            // mounted only while a toolbar query is active.
            .safeAreaInset(edge: .top, spacing: 0) {
                AnyView(transientSearchResultsBar)
            })

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
                        selectedDocumentIds: effectiveWorkflowRunSelection
                    )
                }
            } else {
                // NO legacy WorkflowListView column (Daniel, twice on
                // 2026-08-10: "when you click on a workflow node, it should
                // take you to that editor, not the generic thing you then
                // have to click around in"). The SIDEBAR is the workflow
                // list (#4186); the content column is the node editor, full
                // width.
                //
                // AnyView is LOAD-BEARING on BOTH branches (#4331 / views
                // audit fix #2): the first attempt at this reshape shipped
                // WITHOUT caps and crashed at launch — this case sits inside
                // the same contentView getter whose .library sibling already
                // needed erasure to stop the value-copy recursion.
                if let selectedWorkflow = workflow {
                    AnyView(
                        WorkflowEditor(
                            workflow: selectedWorkflow,
                            editingWorkflow: $editingWorkflow,
                            displayMode: .icon,
                            selectedDocumentIds: effectiveWorkflowRunSelection
                        )
                        .frame(maxWidth: .infinity)
                    )
                } else {
                    AnyView(
                        ContentUnavailableView(
                            "Select a Workflow",
                            systemImage: "flowchart",
                            description: Text("Choose a workflow in the sidebar to edit it")
                        )
                        .frame(maxWidth: .infinity)
                    )
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
