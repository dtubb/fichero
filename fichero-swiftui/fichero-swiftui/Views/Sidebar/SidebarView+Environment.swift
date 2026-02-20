import SwiftUI

// MARK: - Automation Refresh Environment Key

/// Environment key for automation refresh callback (used by editor views to trigger sidebar refresh)
private struct AutomationRefreshKey: EnvironmentKey {
    nonisolated(unsafe) static let defaultValue: (() -> Void)? = nil
}

extension EnvironmentValues {
    /// Callback to refresh automation data (schedules and triggers)
    var automationRefresh: (() -> Void)? {
        get { self[AutomationRefreshKey.self] }
        set { self[AutomationRefreshKey.self] = newValue }
    }
}
