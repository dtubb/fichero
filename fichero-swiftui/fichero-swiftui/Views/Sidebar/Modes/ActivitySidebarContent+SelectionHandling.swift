import SwiftUI

extension ActivitySidebarContent {

    func handleSelection(_ id: String?) {
        guard let id = id else {
            activitySidebarLogger.debug("🔵 Activity selection cleared")
            viewMode = .activity(nil)
            return
        }
        activitySidebarLogger.debug("🔵 Activity selection: \(id)")

        guard id.hasPrefix("run-") else {
            activitySidebarLogger.warning("🔵 Invalid activity ID format (missing run- prefix): \(id)")
            return
        }

        let remainder = String(id.dropFirst("run-".count))

        var runId = remainder
        var childType: ActivityChildType?

        for type in ActivityChildType.allCases {
            let suffix = "-\(type.rawValue)"
            if remainder.hasSuffix(suffix) {
                childType = type
                runId = String(remainder.dropLast(suffix.count))
                break
            }
        }

        activitySidebarLogger.debug("🔵 Parsed runId: \(runId), childType: \(childType?.rawValue ?? "none")")

        if let run = findRun(byId: runId) {
            if let childType = childType {
                activitySidebarLogger.debug("🔵 Setting viewMode to activity run \(runId) with child: \(childType.rawValue)")
                viewMode = .activity(run.toSelectedRun().with(childType: childType))
            } else {
                activitySidebarLogger.debug("🔵 Setting viewMode to activity run \(runId) (overview)")
                viewMode = .activity(run.toSelectedRun())
            }
        } else {
            activitySidebarLogger.warning("🔵 Could not find run with ID: \(runId)")
        }
    }

    func findRun(byId runId: String) -> ActivityRun? {
        for library in libraryManager.openLibraries {
            let groups = runsByWorkflow(
                for: library,
                activeExecutions: activeExecutionsSnapshot,
                historicalRuns: historicalRunsByLibrary
            )
            for runs in groups.values {
                if let run = runs.first(where: { $0.id == runId }) {
                    return run
                }
            }
        }
        return nil
    }
}
