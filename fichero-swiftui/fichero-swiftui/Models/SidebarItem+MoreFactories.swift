import Foundation

// MARK: - SidebarItem Additional Factory Methods

extension SidebarItem {

    static func fromChain(_ chain: WorkflowChain, libraryId: UUID, children: [SidebarItem]? = nil) -> SidebarItem {
        SidebarItem(
            id: "chain:\(chain.id)",
            name: chain.name,
            icon: "link",
            category: .workflow,
            itemType: .chain(chain),
            children: children,
            progress: nil,
            showProgress: false,
            libraryId: libraryId,
            folderPath: "/",  // Chains don't have folder paths yet
            sortOrder: 0,
            isFolder: false
        )
    }

    static func fromComparison(_ comparison: ComparisonSummary, libraryId: UUID, children: [SidebarItem]? = nil) -> SidebarItem {
        // Truncate prompt for display
        let displayName = comparison.prompt.prefix(40) + (comparison.prompt.count > 40 ? "..." : "")
        return SidebarItem(
            id: "comparison:\(comparison.comparisonId)",
            name: String(displayName),
            icon: "arrow.left.arrow.right",
            category: .chat,
            itemType: .comparison(comparison),
            children: children,
            progress: nil,
            showProgress: false,
            libraryId: libraryId,
            folderPath: "/",
            sortOrder: 0,
            isFolder: false
        )
    }

    static func fromSchedule(_ schedule: ScheduleInfo, libraryId: UUID, children: [SidebarItem]? = nil) -> SidebarItem {
        SidebarItem(
            id: "schedule:\(schedule.scheduleId)",
            name: schedule.name,
            icon: schedule.statusIcon,
            category: .automation,
            itemType: .schedule(schedule),
            children: children,
            progress: nil,
            showProgress: false,
            libraryId: libraryId,
            folderPath: "/",
            sortOrder: 0,
            isFolder: false
        )
    }

    static func fromTrigger(_ trigger: TriggerInfo, libraryId: UUID, children: [SidebarItem]? = nil) -> SidebarItem {
        SidebarItem(
            id: "trigger:\(trigger.triggerId)",
            name: trigger.name,
            icon: trigger.statusIcon,
            category: .automation,
            itemType: .trigger(trigger),
            children: children,
            progress: nil,
            showProgress: false,
            libraryId: libraryId,
            folderPath: "/",
            sortOrder: 0,
            isFolder: false
        )
    }

    static func fromBatch(_ batch: BatchInfo, libraryId: UUID, children: [SidebarItem]? = nil) -> SidebarItem {
        let progress = batch.totalItems > 0 ? Double(batch.completedItems) / Double(batch.totalItems) : 0
        return SidebarItem(
            id: "batch:\(batch.batchId)",
            name: batch.name,
            icon: batch.status == "running" ? "play.circle.fill" : "checkmark.circle",
            category: .batch,
            itemType: .batch(batch),
            children: children,
            progress: progress,
            showProgress: batch.status == "running",
            libraryId: libraryId,
            folderPath: "/",
            sortOrder: 0,
            isFolder: false
        )
    }

    static func fromActivityRun(_ activity: ActivityItem, libraryId: UUID, children: [SidebarItem]? = nil) -> SidebarItem {
        SidebarItem(
            id: "activity:\(activity.id)",
            name: activity.name,
            icon: activity.statusIcon,
            category: .activity,
            itemType: .activityRun(activity),
            children: children,
            progress: nil,
            showProgress: activity.status == "running",
            libraryId: libraryId,
            folderPath: "/",
            sortOrder: 0,
            isFolder: false
        )
    }
}
