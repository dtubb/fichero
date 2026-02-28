import Foundation
import SwiftUI

/// Central manager for app features and modules.
/// Allows enabling/disabling major functional blocks for different release stages (e.g., v0.0.1).
@MainActor
class FeatureManager: ObservableObject {
    static let shared = FeatureManager()
    
    /// Global toggle to override all flags for internal development.
    /// In a production release, this would be hardcoded to false.
    @AppStorage("fichero.features.all_enabled") var allFeaturesEnabled: Bool = ProcessInfo.processInfo.environment["FICHERO_ALL_FEATURES"] == "1"
    
    // MARK: - Core Features (v0.0.1)
    
    @Published var isLibraryEnabled: Bool = true
    @Published var isSearchEnabled: Bool = true
    
    // MARK: - Advanced Features (Target: v0.1.0+)
    
    @AppStorage("fichero.features.workflows") private var workflowsEnabledInternal: Bool = false
    @AppStorage("fichero.features.chat") private var chatEnabledInternal: Bool = true
    @AppStorage("fichero.features.agents") private var agentsEnabledInternal: Bool = false
    @AppStorage("fichero.features.automation") private var automationEnabledInternal: Bool = false
    @AppStorage("fichero.features.mcp") private var mcpEnabledInternal: Bool = false
    @AppStorage("fichero.features.activity") private var activityEnabledInternal: Bool = false

    var isWorkflowsEnabled: Bool { allFeaturesEnabled || workflowsEnabledInternal }
    var isChatEnabled: Bool { allFeaturesEnabled || chatEnabledInternal }
    var isAgentsEnabled: Bool { allFeaturesEnabled || agentsEnabledInternal }
    var isAutomationEnabled: Bool { allFeaturesEnabled || automationEnabledInternal }
    var isMCPEnabled: Bool { allFeaturesEnabled || mcpEnabledInternal }
    var isActivityEnabled: Bool { allFeaturesEnabled || activityEnabledInternal }

    private init() {}
    
    /// Reset to v0.0.1 defaults
    func resetToV001() {
        allFeaturesEnabled = false
        workflowsEnabledInternal = false
        chatEnabledInternal = true
        agentsEnabledInternal = false
        automationEnabledInternal = false
        mcpEnabledInternal = false
        activityEnabledInternal = false
    }
}

// MARK: - View Helpers

extension View {
    /// Conditionally shows a view based on a feature flag
    @ViewBuilder
    func featureEnabled(_ isEnabled: Bool) -> some View {
        if isEnabled {
            self
        }
    }
}
