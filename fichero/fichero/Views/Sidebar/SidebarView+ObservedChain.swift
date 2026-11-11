import SwiftUI

// MARK: - SidebarView observer chain
//
// Split out of SidebarView.swift: the struct body was at the type_body_length limit, and one long
// modifier chain also exceeded the type-checker's time limit in Xcode previews.

extension SidebarView {
    /// The sidebar with its observers; the menu, alert and sheet modifiers follow in `body`. Split into four short
    /// chains, `sidebarBase` then `sidebarLoaded` then `sidebarSelectionObserved` then `sidebarObserved`, so the
    /// type-checker sees bounded expressions (builder RED at c34881647: SidebarView.swift:187 type-check time limit)
    /// and Xcode previews compile: their thunk mode rewrites every string literal into a call, which tipped the one
    /// long chain over the limit again.
    var sidebarBase: some View {
        sidebarContent
            .sidebarStyle()
            // Reveal-in-sidebar (2026-08-23, Daniel: "sidebar should have the
            // appropriate folder selected, once library loads"): the restore
            // path — and anything else that lands on a nested folder without
            // clicking sidebar rows — posts this; the sidebar expands the
            // ancestor chain, loads the children so the row EXISTS, and
            // selects it through the same seam a click uses.
            .onReceive(
                NotificationCenter.default.publisher(for: .sidebarRevealDocument)
            ) { note in
                // A library crumb (#5218): that library's top level, selected as its sidebar row is.
                if let raw = note.userInfo?["libraryId"] as? String, let libraryId = UUID(uuidString: raw) {
                    openAsClicked(.library(libraryId), reopen: Self.revealReopens(note))
                    return
                }
                guard let docId = note.userInfo?["documentId"] as? String else { return }
                // A segment to select when the page arrives: a citable reference (#5164), a flow's Next (#5160).
                if let segmentId = note.userInfo?["segmentId"] as? String {
                    windowState.pendingSegmentSelection = .init(documentId: docId, segmentId: segmentId)
                }
                Task { [reopen = Self.revealReopens(note)] in await revealDocument(docId, reopen: reopen) }
            }
            // Suppress the NavigationSplitView sidebar-column title header (#2309).
            // The title is now shown centred in the main window toolbar by another
            // worker; the redundant sidebar column header is removed here.
            .navigationTitle("")
            // Opt-in (FICHERO_PRINT_CHANGES=1): a disappear/appear pair on a click is a re-mount.
            .onAppear {
                if RenderDiagnostics.printChanges { sidebarViewLogger.info("◆ SidebarView appeared") }
            }
            .onDisappear {
                if RenderDiagnostics.printChanges { sidebarViewLogger.info("◆ SidebarView disappeared") }
            }
    }

    /// Loads the caches, observers and per-mode data once the sidebar appears.
    var sidebarLoaded: some View {
        sidebarBase
            .task {
                // Check cancellation before starting
                guard !Task.isCancelled else { return }

                // Build initial caches
                rebuildCaches()

                guard !Task.isCancelled else { return }

                // Subscribe to all library service changes
                setupServiceObservers()

                // Configure item registry handlers
                setupItemRegistry()

                guard !Task.isCancelled else { return }

                // Load chains for workflows sidebar
                if FeatureManager.shared.isWorkflowChainsEnabled {
                    await chainService.loadChains()
                } else {
                    chains = []
                }

                guard !Task.isCancelled else { return }

                // Load automation data (schedules and triggers)
                if FeatureManager.shared.isAutomationEnabled {
                    await loadAutomationData()
                } else {
                    schedules = []
                    triggers = []
                }

                guard !Task.isCancelled else { return }

                // Load historical activity runs for unified Activity section.
                if FeatureManager.shared.isActivityEnabled {
                    await loadActivityData()
                } else {
                    historicalRunsByLibrary = [:]
                }

                guard !Task.isCancelled else { return }

                // Drive a restored (@SceneStorage) selection into the view mode
                // now that caches exist — .onChange(of:) never fired for it
                // because the value didn't change on launch (#2548).
                reconcileRestoredSelection()
            }
    }

    /// Routes a selection, library or load change into the sidebar's mode and caches.
    var sidebarSelectionObserved: some View {
        sidebarLoaded
            .onChange(of: selectionState.selectedDestination) { _, newDestination in
                // Route the live selection change to sidebarMode / viewMode —
                // ONE TURN LATER (#20/#113). AppKit paints the native
                // emphasized (accent) selection platter on mouseDown; our
                // opaque grey platter covers it only when this SwiftUI
                // transaction commits. Routing synchronously kept the
                // transaction open through the whole detail-pane rebuild
                // (137ms measured live, InteractionProfile), so the green
                // platter stayed visible for the entire commit. Deferring the
                // routing lets the cheap highlight frame (grey platter +
                // accent label) paint first; the heavy reroute lands on the
                // next main-actor turn. Rapid re-clicks are safe:
                // handleSelectionChange is idempotent via
                // lastHandledSelectionDestination and main-actor tasks run in
                // enqueue order.
                Task { @MainActor in
                    handleSelectionChange(newDestination, reason: "click")
                }
            }
            .onChange(of: windowState.libraryId) { _, landedLibraryId in
                // The window now shows this library and the content column holds ITS stores:
                // route the cross-library selection that asked for the switch.
                routePendingCrossLibrarySelection(landedLibraryId: landedLibraryId)
            }
            .onChange(of: libraryManager.openLibraries.count) { _, _ in
                // Rebuild when libraries are added/removed
                rebuildCaches()

                // Resubscribe to service changes for new libraries
                setupServiceObservers()
            }
            .onChange(of: libraryManager.createdProjectId) { _, createdId in
                // A project just created is selected, as its row is (#5430), through the seam a click uses.
                guard let createdId, libraryManager.getLibrary(id: createdId) != nil else { return }
                applySidebarSelectionProposal([.library(createdId)])
            }
            .onChange(of: libraryManager.librariesLoadVersion) { _, _ in
                // Rebuild after any library finishes loading its data (#2472).
                // On iPhone, SidebarView.task fires before loadCollections()
                // completes; this is the stable signal that collections are ready.
                rebuildCaches()
                // A restored selection may only now resolve against the freshly
                // built caches — reconcile it into the view mode (#2548).
                reconcileRestoredSelection()
                // The automation and activity loads wait for their library to load; run them again now (#5822).
                Task { @MainActor in
                    if FeatureManager.shared.isAutomationEnabled { await loadAutomationData() }
                    if FeatureManager.shared.isActivityEnabled { await loadActivityData() }
                }
            }
    }

    /// Refreshes mode-specific data when the mode, running executions or activity change.
    var sidebarObserved: some View {
        sidebarSelectionObserved
            .onChange(of: sidebarMode) { _, newMode in
                // Switching sections should allow re-selecting the same item in the
                // new section without onChange being blocked by lastHandledSelectionId
                // (which only guards against same-tick duplicate events, not cross-section
                // re-selection — #646).
                lastHandledSelectionDestination = nil
                // Refresh data when switching to mode-specific sidebars
                // This ensures sidebar shows updated data after editor saves
                if newMode == .automation {
                    Task {
                        guard !Task.isCancelled else { return }
                        guard FeatureManager.shared.isAutomationEnabled else {
                            schedules = []
                            triggers = []
                            return
                        }
                        await loadAutomationData()
                    }
                } else if newMode == .activity {
                    Task {
                        guard !Task.isCancelled else { return }
                        await loadActivityData()
                    }
                }
            }
            .onChange(of: executionObserver.activeExecutions.count) { oldCount, newCount in
                guard FeatureManager.shared.isActivityEnabled else { return }
                // When a run starts or finishes, refresh historical runs so completed items persist.
                guard oldCount != newCount else { return }
                Task { @MainActor in
                    guard !Task.isCancelled else { return }
                    await loadActivityData()
                }
            }
            .onChange(of: libraryManager.globalLibrary?.activityStore.refreshToken ?? 0) { _, _ in
                guard FeatureManager.shared.isActivityEnabled else { return }
                guard case .activity = viewMode else { return }
                Task { @MainActor in
                    await loadActivityData()
                }
            }
    }
}
