import SwiftUI
import OSLog

private let logger = Logger(subsystem: "ca.tubb.Fichero", category: "AutomationSidebarContent")

/// Sidebar content for Automation mode - shows schedules and triggers grouped by library
/// Note: Running Batches are shown in the Batches sidebar, not here
/// Data is managed by parent (SidebarView) using proper Combine observers
struct AutomationSidebarContent: View {
    @EnvironmentObject var apiClient: APIClient
    @EnvironmentObject var windowState: WindowState
    @ObservedObject var libraryManager: LibraryManager

    // Selection binding from parent (following Library pattern)
    @Binding var selectedItemId: String?
    @Binding var viewMode: AppViewMode

    // SidebarState for expansion persistence
    @ObservedObject var sidebarState: SidebarState

    // Rename and delete state
    @ObservedObject var renameState: RenameStateManager
    @ObservedObject var deleteState: DeleteStateManager

    // Data from parent (SidebarView manages loading via Combine pattern)
    let schedules: [ScheduleInfo]
    let triggers: [TriggerInfo]
    let isLoading: Bool
    var onRefresh: (() -> Void)?

    /// Schedules grouped by library (currently all under Global)
    private var schedulesByLibrary: [UUID: [ScheduleInfo]] {
        // swiftlint:disable:next todo
        // TODO: When backend supports library filtering, group appropriately
        [LibraryManager.globalLibraryId: schedules]
    }

    /// Triggers grouped by library (currently all under Global)
    private var triggersByLibrary: [UUID: [TriggerInfo]] {
        // swiftlint:disable:next todo
        // TODO: When backend supports library filtering, group appropriately
        [LibraryManager.globalLibraryId: triggers]
    }

    var body: some View {
        List(selection: $selectedItemId) {
            if isLoading && schedulesByLibrary.isEmpty && triggersByLibrary.isEmpty {
                ProgressView()
                    .frame(maxWidth: .infinity, alignment: .center)
                    .listRowSeparator(.hidden)
            } else {
                // Show libraries with their schedules and triggers
                ForEach(libraryManager.openLibraries, id: \.id) { library in
                    librarySection(library)
                }
            }
        }
        .listStyle(.sidebar)
        .scrollContentBackground(.hidden)
        .onChange(of: selectedItemId) { _, newId in
            handleSelection(newId)
        }
    }

    // MARK: - Library Section

    @ViewBuilder
    private func librarySection(_ library: LibraryManager.LibraryReference) -> some View {
        let schedules = schedulesByLibrary[library.id] ?? []
        let triggers = triggersByLibrary[library.id] ?? []
        let totalCount = schedules.count + triggers.count

        Section {
            // Build SidebarItems for schedules
            let scheduleItems = schedules.map { schedule in
                SidebarItem.fromSchedule(schedule, libraryId: windowState.libraryId)
            }

            // Build SidebarItems for triggers
            let triggerItems = triggers.map { trigger in
                SidebarItem.fromTrigger(trigger, libraryId: windowState.libraryId)
            }

            // Schedules (flat list)
            ForEach(scheduleItems) { item in
                SidebarItemRow(
                    item: item,
                    allCachedItems: scheduleItems + triggerItems,
                    expandedItems: Binding(
                        get: { sidebarState.expandedItems },
                        set: { sidebarState.expandedItems = $0 }
                    ),
                    selectedItemId: $selectedItemId,
                    renameState: renameState,
                    deleteState: deleteState,
                    libraryManager: libraryManager,
                    onAutomationPause: scheduleActionCallback(item, .pause),
                    onAutomationResume: scheduleActionCallback(item, .resume),
                    onAutomationTrigger: scheduleActionCallback(item, .trigger)
                )
                .tag(item.id)
            }

            // Triggers (flat list)
            ForEach(triggerItems) { item in
                SidebarItemRow(
                    item: item,
                    allCachedItems: scheduleItems + triggerItems,
                    expandedItems: Binding(
                        get: { sidebarState.expandedItems },
                        set: { sidebarState.expandedItems = $0 }
                    ),
                    selectedItemId: $selectedItemId,
                    renameState: renameState,
                    deleteState: deleteState,
                    libraryManager: libraryManager,
                    onAutomationPause: triggerActionCallback(item, .pause),
                    onAutomationResume: triggerActionCallback(item, .resume),
                    onAutomationTrigger: nil  // Triggers don't have "run now"
                )
                .tag(item.id)
            }

            // Empty state
            if schedules.isEmpty && triggers.isEmpty && !isLoading {
                Text("No automation items")
                    .foregroundStyle(.secondary)
                    .font(.caption)
                    .padding(.vertical, 4)
            }
        } header: {
            LibrarySectionHeader(
                library: library,
                itemCount: totalCount,
                isCurrentLibrary: library.id == windowState.libraryId
            )
        }
    }

    // MARK: - Selection Handling

    private func handleSelection(_ id: String?) {
        guard let id = id else { return }

        if id.hasPrefix("schedule:") {
            let scheduleId = String(id.dropFirst("schedule:".count))
            let allSchedules = schedulesByLibrary.values.flatMap { $0 }
            if let schedule = allSchedules.first(where: { $0.scheduleId == scheduleId }) {
                viewMode = .schedule(schedule)
            }
        } else if id.hasPrefix("trigger:") {
            let triggerId = String(id.dropFirst("trigger:".count))
            let allTriggers = triggersByLibrary.values.flatMap { $0 }
            if let trigger = allTriggers.first(where: { $0.triggerId == triggerId }) {
                viewMode = .trigger(trigger)
            }
        }
    }

    // MARK: - Action Callbacks

    /// Create a callback for schedule actions (pause/resume/trigger)
    /// Returns nil if the item is not a schedule
    private func scheduleActionCallback(_ item: SidebarItem, _ action: ScheduleAction) -> (() -> Void)? {
        guard case .schedule(let schedule) = item.itemType else { return nil }

        return {
            Task {
                do {
                    guard let library = libraryManager.openLibraries.first else {
                        logger.error("No library available for schedule action")
                        return
                    }
                    let automationService = library.automationService
                    switch action {
                    case .pause:
                        _ = try await automationService.pauseSchedule(scheduleId: schedule.scheduleId)
                    case .resume:
                        _ = try await automationService.resumeSchedule(scheduleId: schedule.scheduleId)
                    case .trigger:
                        _ = try await automationService.triggerSchedule(scheduleId: schedule.scheduleId)
                    case .delete:
                        // Delete is handled by SidebarItemRow's performDelete
                        break
                    }
                    // Trigger parent to reload automation data
                    await MainActor.run {
                        onRefresh?()
                    }
                } catch {
                    logger.error("Failed to perform schedule action: \(error.localizedDescription)")
                }
            }
        }
    }

    /// Create a callback for trigger actions (pause/resume)
    /// Returns nil if the item is not a trigger
    private func triggerActionCallback(_ item: SidebarItem, _ action: TriggerAction) -> (() -> Void)? {
        guard case .trigger(let trigger) = item.itemType else { return nil }

        return {
            Task {
                do {
                    guard let library = libraryManager.openLibraries.first else {
                        logger.error("No library available for trigger action")
                        return
                    }
                    let automationService = library.automationService
                    switch action {
                    case .pause:
                        _ = try await automationService.pauseTrigger(triggerId: trigger.triggerId)
                    case .resume:
                        _ = try await automationService.resumeTrigger(triggerId: trigger.triggerId)
                    case .delete:
                        // Delete is handled by SidebarItemRow's performDelete
                        break
                    }
                    // Trigger parent to reload automation data
                    await MainActor.run {
                        onRefresh?()
                    }
                } catch {
                    logger.error("Failed to perform trigger action: \(error.localizedDescription)")
                }
            }
        }
    }
}

#Preview {
    AutomationSidebarContent(
        libraryManager: .shared,
        selectedItemId: .constant(nil),
        viewMode: .constant(.automation),
        sidebarState: SidebarState(),
        renameState: RenameStateManager(),
        deleteState: DeleteStateManager(),
        schedules: [],
        triggers: [],
        isLoading: false,
        onRefresh: nil
    )
    .environmentObject(APIClient())
    .environmentObject(WindowState(libraryId: LibraryManager.globalLibraryId))
    .frame(width: 280, height: 500)
}
