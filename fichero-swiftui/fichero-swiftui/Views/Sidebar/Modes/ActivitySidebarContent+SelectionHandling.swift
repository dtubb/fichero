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

        let runToken = String(id.dropFirst("run-".count))
        activitySidebarLogger.debug("🔵 Parsed run token: \(runToken)")

        if let run = findRun(bySelectionToken: runToken) {
            activitySidebarLogger.debug("🔵 Setting viewMode to activity run \(run.runId) (overview)")
            viewMode = .activity(run.toSelectedRun())
        } else {
            activitySidebarLogger.warning("🔵 Could not find run for selection token: \(runToken)")
        }
    }

    func findRun(bySelectionToken token: String) -> ActivityRun? {
        for library in libraryManager.openLibraries {
            let groups = runsByWorkflow(
                for: library,
                activeExecutions: activeExecutionsSnapshot,
                historicalRuns: historicalRunsByLibrary
            )
            for runs in groups.values {
                if let run = runs.first(where: { $0.id == token || $0.runId == token }) {
                    return run
                }
            }
        }
        return nil
    }
}
