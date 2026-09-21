import Combine
import OSLog
import SwiftUI

/// Structured logger for sidebar observer operations
private let logger = Logger(subsystem: "app.fichero.fichero", category: "SidebarObservers")

// MARK: - Service Observers and Data Loading Extension

extension SidebarView {
    /// Observe every open library's sidebar-driving stores, plus the global chain service.
    ///
    /// Every store here is `@Observable` (#1851, #1911, #2960), so there is no Combine publisher
    /// to subscribe to — each observer is a `withObservationTracking` chain, armed through
    /// `observerChains` so this call can SUPERSEDE the chains a previous call armed. It runs from
    /// the view's `.task` and again on every open-library-count change; before the token, each
    /// run stacked another immortal set on top (see `SidebarObserverChains`).
    func setupServiceObservers() {
        observerChains.reset()

        for library in libraryManager.openLibraries {
            let libraryId = library.id
            let documentStore = library.documentStore
            observerChains.observe(
                signature: {
                    // `sidebarTreeSignature` reads `sidebarDocuments` (collections + the
                    // children cache). `childrenCache` is @ObservationIgnored, so a change-stream
                    // splice that lands rows ONLY there registers nothing (the 2026-08-24
                    // folder-drop that never grew a chevron); `revision` is the store's
                    // observable proxy for exactly those containers, and `currentDocuments`
                    // churns on status polls the signature deliberately ignores (#3862). Read
                    // all three so the chain wakes; the signature decides whether to rebuild.
                    _ = documentStore.collections
                    _ = documentStore.currentDocuments
                    _ = documentStore.revision
                    return sidebarTreeSignature(for: library)
                },
                onChange: { rebuildCaches(for: libraryId, reason: "documents") }
            )

            let savedSearchService = library.savedSearchService
            observerChains.observe(
                signature: { savedSearchService.savedSearches.hashValue },
                onChange: { rebuildCaches(for: libraryId, reason: "savedSearches") }
            )

            let conversationService = library.conversationService
            observerChains.observe(
                signature: { conversationService.conversations.hashValue },
                onChange: { rebuildCaches(for: libraryId, reason: "conversations") }
            )

            let workflowStore = library.workflowStore
            observerChains.observe(
                signature: { workflowStore.workflows.hashValue },
                onChange: { rebuildCaches(for: libraryId, reason: "workflows") }
            )
        }

        // The global chain list is mirrored into the view's own `chains`, not rebuilt from.
        let service = chainService
        observerChains.observe(
            signature: { service.chains.hashValue },
            onChange: { chains = service.chains }
        )
    }

    /// Load automation data (schedules and triggers)
    func loadAutomationData() async {
        guard !automationIsLoading else { return }
        automationIsLoading = true
        defer { automationIsLoading = false }
        automationLoadError = nil

        do {
            guard let library = libraryManager.openLibraries.first else {
                logger.warning("No library available to load automation data")
                automationLoadError = "No library available for Automation."
                return
            }
            let automationService = library.automationService
            async let schedulesTask: [ScheduleInfo] = automationService.listSchedules(limit: 100)
            async let triggersTask: [TriggerInfo] = automationService.listTriggers(limit: 100)

            let (loadedSchedules, loadedTriggers) = try await (schedulesTask, triggersTask)
            schedules = loadedSchedules
            triggers = loadedTriggers
            automationLoadError = nil
            logger.info("Loaded \(loadedSchedules.count) schedules and \(loadedTriggers.count) triggers")
        } catch {
            logger.error("Failed to load automation data: \(error.localizedDescription)")
            automationLoadError = error.localizedDescription
        }
    }

    /// Load activity data (historical workflow runs)
    func loadActivityData() async {
        guard !activityIsLoading else { return }
        activityIsLoading = true
        defer { activityIsLoading = false }
        activityLoadError = nil

        let types = [
            "workflow_started",
            "workflow_completed",
            "workflow_failed",
            "workflow_cancelled"
        ]
        let since = Date().addingTimeInterval(-7 * 24 * 3600)
        var failures: [String] = []

        // Load activity from each open library
        for library in libraryManager.openLibraries {
            guard !Task.isCancelled else { return }

            do {
                let activityService = library.activityService
                let runs = try await activityService.queryActivities(
                    types: types,
                    since: since,
                    limit: 100
                )

                guard !Task.isCancelled else { return }

                historicalRunsByLibrary[library.id] = runs
                logger.info("Loaded \(runs.count) activity items from \(library.displayName)")
            } catch {
                logger.error("Failed to load activity from \(library.displayName): \(error.localizedDescription)")
                failures.append("\(library.displayName): \(error.localizedDescription)")
            }
        }
        activityLoadError = failures.isEmpty ? nil : failures.joined(separator: "\n")
    }

    /// Configure item registry handlers
    func setupItemRegistry() {
        itemRegistry.createFolder = handleCreateNewFolder
        itemRegistry.importFiles = {
            importFiles(mode: .link)  // Default to link mode from Add menu
        }
        itemRegistry.createChat = createNewChat
        itemRegistry.createWorkspace = createNewWorkspace
        itemRegistry.createComparison = createNewComparison
        if FeatureManager.shared.isWorkflowChainsEnabled {
            itemRegistry.createWorkflow = createNewWorkflow
            itemRegistry.createChain = createNewChain
        } else {
            // Keep base workflow creation available, but gate chain creation.
            itemRegistry.createWorkflow = createNewWorkflow
            itemRegistry.createChain = nil
        }

        if FeatureManager.shared.isAutomationEnabled {
            itemRegistry.createSchedule = createNewSchedule
            itemRegistry.createTrigger = createNewTrigger
        } else {
            itemRegistry.createSchedule = nil
            itemRegistry.createTrigger = nil
        }
    }
}
