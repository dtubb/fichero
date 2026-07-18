import Combine
import OSLog
import SwiftUI

/// Structured logger for sidebar observer operations
private let logger = Logger(subsystem: "app.fichero.fichero", category: "SidebarObservers")

// MARK: - Service Observers and Data Loading Extension

extension SidebarView {
    /// Set up observers for all library services using Combine
    /// Uses $property publishers (not objectWillChange) to ensure we read AFTER mutations complete
    func setupServiceObservers() {
        // Cancel existing subscriptions
        cancellables.removeAll()

        // Observe changes in all libraries' services
        for library in libraryManager.openLibraries {
            // Observe document changes. DocumentStore is @Observable (#1851),
            // so it has no Combine `$collections` publisher — use Observation
            // tracking and re-arm after each mutation.
            observeDocumentStore(library.documentStore, libraryId: library.id)

            // Observe saved search + conversation changes. Both services are now
            // @Observable (#2960), so they have no Combine `$` publishers — use
            // Observation tracking, re-armed after each mutation.
            observeSavedSearchService(library.savedSearchService, libraryId: library.id)
            observeConversationService(library.conversationService, libraryId: library.id)

            // Observe workflow changes. WorkflowStore is now @Observable (#1911),
            // so it has no Combine `$workflows` publisher — use Observation
            // tracking, re-armed after each fire, to mirror the old behaviour
            // (rebuild caches AFTER a workflow mutation completes).
            observeWorkflowStore(library.workflowStore, libraryId: library.id)
        }

        // Observe chain changes (global ChainService, now @Observable #2960).
        observeChainService(chainService)
    }

    /// Observe an @Observable ChainService's `chains` array and mirror it into
    /// the sidebar's local `chains`. Re-arm after each fire (one-shot tracking).
    func observeChainService(_ service: ChainService) {
        withObservationTracking {
            _ = service.chains
        } onChange: {
            Task { @MainActor in
                chains = service.chains
                observeChainService(service)
            }
        }
    }

    /// Observe an @Observable SavedSearchService's `savedSearches` and rebuild
    /// caches after each mutation. Re-arm after each fire (one-shot tracking).
    func observeSavedSearchService(_ service: SavedSearchService, libraryId: UUID) {
        withObservationTracking {
            _ = service.savedSearches
        } onChange: {
            Task { @MainActor in
                rebuildCaches(for: libraryId)
                observeSavedSearchService(service, libraryId: libraryId)
            }
        }
    }

    /// Observe an @Observable ConversationService's `conversations` and rebuild
    /// caches after each mutation. Re-arm after each fire (one-shot tracking).
    func observeConversationService(_ service: ConversationService, libraryId: UUID) {
        withObservationTracking {
            _ = service.conversations
        } onChange: {
            Task { @MainActor in
                rebuildCaches(for: libraryId)
                observeConversationService(service, libraryId: libraryId)
            }
        }
    }

    /// Observe an @Observable WorkflowStore's `workflows` array and rebuild the
    /// sidebar caches when it changes. `withObservationTracking` fires once, so
    /// we re-arm it on each change to keep observing for the view's lifetime.
    func observeWorkflowStore(_ store: WorkflowStore, libraryId: UUID) {
        withObservationTracking {
            _ = store.workflows
        } onChange: {
            Task { @MainActor in
                rebuildCaches(for: libraryId)
                observeWorkflowStore(store, libraryId: libraryId)
            }
        }
    }

    /// Observe an @Observable DocumentStore's sidebar-driving arrays and
    /// rebuild caches when either changes. Re-arm after each fire because
    /// `withObservationTracking` is one-shot.
    func observeDocumentStore(_ store: DocumentStore, libraryId: UUID) {
        withObservationTracking {
            _ = store.collections
            _ = store.currentDocuments
            _ = store.childrenCache
        } onChange: {
            Task { @MainActor in
                // #3862: currentDocuments (and status overrides on collections)
                // churn on every processing poll, but they don't shape the sidebar
                // tree. Only rebuild when the tree-relevant signature actually
                // changed — otherwise a status-poll storm rebuilt the whole tree
                // and re-rendered the entire List for no visible change.
                if let library = libraryManager.getLibrary(id: libraryId) {
                    let signature = sidebarTreeSignature(for: library)
                    if sidebarTreeSignatures[libraryId] != signature {
                        rebuildCaches(for: libraryId)
                    }
                }
                observeDocumentStore(store, libraryId: libraryId)
            }
        }
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
        itemRegistry.createSearch = createNewSearch
        itemRegistry.createChat = createNewChat
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
