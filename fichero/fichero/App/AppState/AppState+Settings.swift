import Foundation
import SwiftUI
#if canImport(AppKit)
import AppKit
#endif

extension AppState {
    func openSettings(tab: SettingsTab) {
        selectedSettingsTab = resolvedSettingsTab(for: tab)
        #if canImport(AppKit)
        NSApp.sendAction(Selector(("showSettingsWindow:")), to: nil, from: nil)
        #endif
    }

    private func resolvedSettingsTab(for requestedTab: SettingsTab) -> SettingsTab {
        let featureManager = FeatureManager.shared
        switch requestedTab {
        case .mcp where !featureManager.isMCPEnabled:
            return .aiModels
        case .integrations where !featureManager.isIntegrationsEnabled:
            return .aiModels
        default:
            return requestedTab
        }
    }
}
