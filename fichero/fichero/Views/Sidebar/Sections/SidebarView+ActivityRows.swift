import SwiftUI

// MARK: - Activity run resolution
//
// Activity no longer renders as sidebar rows (the run history moved out of the
// tree). What remains here is only the lookup the LIVE activity view-mode needs:
// `SidebarView+SelectionHandling` resolves a `.run` destination to its
// `ActivityRun` via `unifiedSelectedRun`. The old row grid / cell / tap-select
// code was retired with the one-unified-node-list change.

extension SidebarView {
    @MainActor
    func unifiedActivityRuns(for library: LibraryManager.LibraryReference) -> [ActivityRun] {
        runsByWorkflow(
            for: library,
            activeExecutions: executionObserver.activeExecutions,
            historicalRuns: historicalRunsByLibrary
        )
        .values
        .flatMap { $0 }
        .sorted { $0.timestamp > $1.timestamp }
    }

    @MainActor
    func unifiedSelectedRun(forSidebarId sidebarId: String) -> ActivityRun? {
        guard sidebarId.hasPrefix("run:") else { return nil }
        let runSidebarId = String(sidebarId.dropFirst("run:".count))
        for library in libraryManager.openLibraries {
            if let run = unifiedActivityRuns(for: library).first(where: { $0.id == runSidebarId }) {
                return run
            }
        }
        return nil
    }
}
