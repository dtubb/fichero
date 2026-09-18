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

    /// The library column — the centre content for BOTH .library and .chat
    /// modes (2026-08-12: chat no longer takes over; its conversation lives
    /// in the row's chat pane while this column keeps the workspace).
    @ViewBuilder
    func libraryContentColumn(pinnedLibrary: Binding<PinnedLibraryScope?>) -> some View {
        // #2960: @Observable via @Environment has no projected binding —
        // @Bindable gives `$viewSettings.libraryLayout`.
        @Bindable var viewSettings = viewSettings
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
            documents: LibraryPanePin.effectiveDocuments(
                pinned: pinnedLibrary.wrappedValue,
                live: activeSearchQuery == nil ? selectedDocuments : searchResultDocuments
            ),
            contentCollection: sidebarContentCollection,
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
            defaultDisplayMode: viewDisplayMode,
            availableDisplayModes: availableViewDisplayModes,
            onChangeDisplayMode: { updateViewDisplayMode($0) },
            // X on the library head = hide the library list pane, the same
            // seam as the toolbar toggle; absent when it's the last pane.
            onClosePane: LibraryPaneToggleModel(paneVisibility: paneVisibility).canHide
                ? { withAnimation(FrameAnimation.snappy) { setLibraryPaneVisible(false) } }
                : nil,
            isPanePinned: Binding(
                get: { LibraryPanePin.isPinned(pinned: pinnedLibrary.wrappedValue) },
                set: { pin in
                    // Freeze-on-current: capture the EXACT rows + folder showing
                    // now (the same 4-value snapshot as before F3), into THIS
                    // split half's own @State via the binding.
                    pinnedLibrary.wrappedValue = pin
                        ? PinnedLibraryScope(
                            documents: activeSearchQuery == nil ? selectedDocuments : searchResultDocuments,
                            folderId: sidebarSelectionState.selectedItemId
                        )
                        : nil
                }
            ),
            folderId: LibraryPanePin.effectiveFolderId(
                pinned: pinnedLibrary.wrappedValue,
                live: sidebarSelectionState.selectedItemId
            ),
            onRequestFocus: { focusedPane = .content; paneFocusHint = .content },
            onRequestPreviousPaneFocus: { cyclePaneFocus(reverse: true) },
            onRequestNextPaneFocus: { cyclePaneFocus(reverse: false) },
            onNavigateInto: { doc in navigateToDocument(doc) },
            onPageFocus: { doc in
                if pageFocusDocument?.id != doc.id {
                    pageFocusDocument = doc
                }
            },
            onRevealSearchResult: { doc in revealSearchResult(doc) },
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
            searchHitCounts: transientSearchHitCounts,
            searchRowHits: transientSearchRowHits
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
        .modifier(windowEnvironment)
        // Keep the library surface inside the content column across every
        // preview/sidebar layout variant; without this, list/table rows can
        // paint under the shell sidebar or off the left window edge (#3336).
        .clipped()
        // Transient-search chrome (#4106 S2/S9/S5): honest result count,
        // Load More, explicit Save Search, and the engine's error detail —
        // mounted only while a toolbar query is active.
        .safeAreaInset(edge: .top, spacing: 0) {
            AnyView(transientSearchResultsBar)
        }
        .safeAreaInset(edge: .top, spacing: 0) {
            AnyView(openPreviewAffordanceBar(for: viewMode))
        })
    }

    /// #4705 "4a-follow": names what is not shown and offers the ONE explicit
    /// action that adds it back — `m2p.open-affordance-adds-missing-preview-pane`.
    /// Mirrors `transientSearchResultsBar`'s structural invariant (crash,
    /// 2026-07-27): the conditional lives INSIDE a constant outer `VStack` so
    /// mounting/dismissing the banner only inserts/removes a child of a
    /// stable root under the `AnyView` erasure at the `.safeAreaInset`
    /// boundary above, rather than alternating the erased view's own type.
    @ViewBuilder
    private func openPreviewAffordanceBar(for viewMode: AppViewMode) -> some View {
        VStack(spacing: 0) {
            if PaneContentPlan.missingPreviewSurface(for: viewMode, hasPreviewLeaf: paneVisibility.canvas) != nil {
                HStack(spacing: 12) {
                    Text("This opens in the \(PaneSpec.Kind.preview.title) pane, which is closed.")
                        .font(.callout)
                        .foregroundStyle(.secondary)
                    Spacer()
                    Button("Open in \(PaneSpec.Kind.preview.title)") {
                        setPaneVisible(.canvas, true)
                    }
                    .font(.body)
                    .accessibilityIdentifier("library.openPreviewAffordance")
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
                .background(.bar)
            }
        }
    }

    @ViewBuilder
    var contentView: some View {
        // #2960: ViewSettings is @Observable via @Environment, which has no
        // projected binding — @Bindable gives `$viewSettings.libraryLayout`.
        @Bindable var viewSettings = viewSettings
        // Knowledge Graph mode intercept DELETED (#4705 increment 3): the
        // `.knowledgeGraph` sidebar mode retired; entity/claim browsing
        // lives in the library-wide Entities/Claims tables via the ordinary
        // `.library` routing below.
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
            // F3: the pin lives PER split half in the host, so splitting the
            // library and pinning one half no longer pins both. Built here (a
            // leaf of `contentView`, which is re-instantiated per SplittablePane
            // sub-pane), so each half gets its own @State; non-split layouts
            // simply have one instance.
            LibrarySplitPaneHost(clearToken: libraryPinClearToken) { pinnedLibrary in
                libraryContentColumn(pinnedLibrary: pinnedLibrary)
            }

        case .chat:
            // NO takeover (Daniel 2026-08-12): selecting a chat keeps the
            // library column; the conversation renders in the row's CHAT
            // PANE (PaneSpec .chat reads viewMode for it). The library shows
            // the last-browsed listing, so the workspace never collapses.
            LibrarySplitPaneHost(clearToken: libraryPinClearToken) { pinnedLibrary in
                libraryContentColumn(pinnedLibrary: pinnedLibrary)
            }

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
                // #4705 increment 2: the Library pane is ALWAYS the
                // navigator now, matching `.library`/`.chat` above —
                // `WorkflowEditor` moved to the Preview pane
                // (`widescreenCanvasPaneContent`, `ContentView+DetailLayout.
                // swift`) and the Reader shows the run log
                // (`WorkflowOutputLog`). No more "Select a Workflow"
                // placeholder here: the sidebar IS the workflow list
                // (#4186), and an empty selection just leaves the Library
                // showing whatever it already showed — the no-collapse
                // ruling applied at its sharpest edge.
                LibrarySplitPaneHost(clearToken: libraryPinClearToken) { pinnedLibrary in
                    libraryContentColumn(pinnedLibrary: pinnedLibrary)
                }
            }

        // #4705 increment 4a: `.chain`/`.batches`/`.schedule`/`.trigger` never
        // had a compact-specific push-stack (only `.workflow`/`.research`/
        // `.activity` did) — the Library pane is ALWAYS the navigator for
        // them now, same `LibrarySplitPaneHost` pattern as `.chat`/
        // `.workflow`. Their real content (`ChainEditorView`/`BatchRunView`/
        // `ScheduleDetailView`/`TriggerDetailView`, unchanged) moved to the
        // Preview pane (`widescreenCanvasPaneContent`,
        // `ContentView+DetailLayout.swift`) — including the "Create Chain"
        // empty state for a nil chain, relocated not deleted.
        // `.batch` and the `.automation` placeholder DELETED (#4705
        // increment 4a): `.batch` always redirected to Activity anyway
        // (SidebarViewTypes.swift); automation with nothing selected now
        // just leaves the Library showing, matching `.workflow(nil)`'s
        // no-collapse rule — there is no automation NODE to placeholder for.
        case .chain, .batches, .automation, .schedule, .trigger:
            LibrarySplitPaneHost(clearToken: libraryPinClearToken) { pinnedLibrary in
                libraryContentColumn(pinnedLibrary: pinnedLibrary)
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
                // #4705 increment 4a: Library stays the navigator; the
                // Preview pane mounts `ActivityDetailView` directly (the
                // SAME component the compact flow above and
                // `ActivityDetailWindow.swift` already trust) instead of
                // launching a separate window via the now-deleted
                // `ActivityWindowLauncherView`.
                LibrarySplitPaneHost(clearToken: libraryPinClearToken) { pinnedLibrary in
                    libraryContentColumn(pinnedLibrary: pinnedLibrary)
                }
            }

        }
        }
    }
}

// MARK: - Library pane pin resolution (F3)

/// Pure pin-decision for the library pane, extracted so the F3 behaviour is
/// unit-testable without a running view — the sibling of `PreviewPanePin`. A
/// pane resolves to its pinned snapshot when one exists, otherwise the live
/// selection, so two `LibrarySplitPaneHost` instances holding DIFFERENT pin
/// state resolve to different scopes from the same live selection (independent
/// per-split pinning). The reset rule is likewise pure: a pane clears its pin
/// when ContentView's monotonic clear token advances past what it last saw.
enum LibraryPanePin {
    /// Rows the pane shows: the pinned snapshot's frozen set wins over live.
    static func effectiveDocuments(
        pinned: PinnedLibraryScope?, live: [Document]
    ) -> [Document] {
        pinned?.documents ?? live
    }

    /// Folder the pane is scoped to: the pinned snapshot's folder wins over live.
    static func effectiveFolderId(
        pinned: PinnedLibraryScope?, live: String?
    ) -> String? {
        pinned?.folderId ?? live
    }

    /// Whether the pane is pinned — a snapshot has been captured.
    static func isPinned(pinned: PinnedLibraryScope?) -> Bool {
        pinned != nil
    }

    /// A pane releases its pin when the cross-cutting reset token advances
    /// (ContentView bumps it on a new search — see ContentView+ActionsImport).
    static func shouldClear(lastSeenToken: Int, currentToken: Int) -> Bool {
        currentToken != lastSeenToken
    }
}

// MARK: - Library split-pane host (F3)

/// Per-split-pane owner of the library pin. Built INSIDE `contentView` (which
/// is re-instantiated per SplittablePane sub-pane), so each sub-instance gets
/// its own `@State` — exactly like `PreviewSplitPaneHost` / `ReadingPaneView`.
/// Splitting the library and pinning one half no longer pins both, because the
/// pin no longer lives on the single ContentView above the split boundary.
///
/// The pin is a frozen snapshot captured at pin time (the head's binding setter
/// captures the current rows + folder). The cross-cutting clear that used to be
/// a direct `pinnedLibrary = nil` on ContentView is now the `clearToken`: when
/// it advances, each host releases its OWN pin.
private struct LibrarySplitPaneHost<Content: View>: View {
    let clearToken: Int
    let content: (Binding<PinnedLibraryScope?>) -> Content

    @State private var pinnedLibrary: PinnedLibraryScope?
    @State private var seenClearToken: Int = 0

    var body: some View {
        content($pinnedLibrary)
            // Baseline the token when this half mounts, so a bump that happened
            // before it appeared does not wipe a pin it never had.
            .onAppear { seenClearToken = clearToken }
            .onChange(of: clearToken) { _, newToken in
                if LibraryPanePin.shouldClear(
                    lastSeenToken: seenClearToken, currentToken: newToken
                ) {
                    pinnedLibrary = nil
                    seenClearToken = newToken
                }
            }
    }
}

// MARK: - Previews

// The host draws nothing of its own — it holds a library pin and clears it when the
// token bumps. So the preview renders the STATE it carries: what a pane sees through
// the binding, and that clearing flows back. `private` types are visible to a
// `#Preview` in the same file.
#Preview("Library split pane host — the pin it carries") {
    LibrarySplitPaneHost(clearToken: 0) { pinned in
        VStack(spacing: 8) {
            Text(pinned.wrappedValue == nil ? "No pinned library" : "Library pinned")
                .font(.callout)
            Button("Clear pin") { pinned.wrappedValue = nil }
        }
        .padding()
        .frame(width: 280, height: 120)
    }
}
