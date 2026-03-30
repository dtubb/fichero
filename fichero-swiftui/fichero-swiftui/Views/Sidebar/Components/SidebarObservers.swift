import Combine
import OSLog
import SwiftUI

/// Structured logger for sidebar observer operations
private let logger = Logger(subsystem: "com.fichero.app", category: "SidebarObservers")

// MARK: - Service Observers and Data Loading Extension

extension SidebarView {
    /// Set up observers for all library services using Combine
    /// Uses $property publishers (not objectWillChange) to ensure we read AFTER mutations complete
    func setupServiceObservers() {
        // Cancel existing subscriptions
        cancellables.removeAll()

        // Observe changes in all libraries' services
        for library in libraryManager.openLibraries {
            // Observe document changes - use $collections which fires AFTER mutation
            library.documentStore.$collections
                .dropFirst()  // Skip initial value
                .receive(on: RunLoop.main)
                .sink { _ in rebuildCaches() }
                .store(in: &cancellables)

            // Observe saved search changes
            library.savedSearchServiceGenerated.$savedSearches
                .dropFirst()
                .receive(on: RunLoop.main)
                .sink { _ in rebuildCaches() }
                .store(in: &cancellables)

            // Observe conversation changes
            library.conversationServiceGenerated.$conversations
                .dropFirst()
                .receive(on: RunLoop.main)
                .sink { _ in rebuildCaches() }
                .store(in: &cancellables)

            // Observe workflow changes - use $workflows which fires AFTER mutation
            library.workflowStore.$workflows
                .dropFirst()
                .receive(on: RunLoop.main)
                .sink { _ in rebuildCaches() }
                .store(in: &cancellables)
        }

        // Observe chain changes (global ChainService)
        chainService.$chains
            .dropFirst()
            .receive(on: RunLoop.main)
            .sink { newChains in
                chains = newChains
            }
            .store(in: &cancellables)
    }

    /// Load automation data (schedules and triggers)
    func loadAutomationData() async {
        guard !automationIsLoading else { return }
        automationIsLoading = true
        defer { automationIsLoading = false }

        do {
            guard let library = libraryManager.openLibraries.first else {
                logger.warning("No library available to load automation data")
                return
            }
            let automationService = library.automationService
            async let schedulesTask: [ScheduleInfo] = automationService.listSchedules(limit: 100)
            async let triggersTask: [TriggerInfo] = automationService.listTriggers(limit: 100)

            let (loadedSchedules, loadedTriggers) = try await (schedulesTask, triggersTask)
            schedules = loadedSchedules
            triggers = loadedTriggers
            logger.info("Loaded \(loadedSchedules.count) schedules and \(loadedTriggers.count) triggers")
        } catch {
            logger.error("Failed to load automation data: \(error.localizedDescription)")
        }
    }

    /// Load batch data
    func loadBatchData() async {
        guard !batchesIsLoading else { return }
        batchesIsLoading = true
        defer { batchesIsLoading = false }

        do {
            guard let library = libraryManager.openLibraries.first else {
                logger.warning("No library available for loading batches")
                return
            }
            batches = try await library.batchService.listBatchesAsInfo(status: nil, limit: 100)
            logger.info("Loaded \(batches.count) batches")
        } catch {
            logger.error("Failed to load batch data: \(error.localizedDescription)")
        }
    }

    /// Load activity data (historical workflow runs)
    func loadActivityData() async {
        guard !activityIsLoading else { return }
        activityIsLoading = true
        defer { activityIsLoading = false }

        let types = [
            "workflow_completed",
            "workflow_failed",
            "workflow_cancelled"
        ]
        let since = Date().addingTimeInterval(-7 * 24 * 3600)

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
            }
        }
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
