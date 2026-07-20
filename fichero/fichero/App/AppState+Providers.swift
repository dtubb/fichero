import FicheroAPIClient
import Foundation
import OSLog

extension AppState {
    func loadProviders() async {
        guard FeatureManager.shared.isVisible(.providers) else {
            providers = []
            hasCheckedProviders = true
            return
        }
        do {
            providers = try await providerService.listProviders()

            // On first check, if no providers configured, remember it's a
            // first-launch setup — but do NOT auto-present the sheet here.
            // loadProviders() runs during launch; presenting a sheet while the
            // main window's NSToolbar is still doing its first layout re-enters
            // the toolbar update and double-inserts an item, crashing at launch
            // on macOS 27 (#3163). Users add a provider from Settings ▸ Providers.
            if !hasCheckedProviders && providers.isEmpty {
                isFirstLaunchProviderSetup = true
            }

            hasCheckedProviders = true
        } catch {
            logger.error("Failed to load providers: \(error.localizedDescription)")
            hasCheckedProviders = true
        }
    }

    /// Show Add Provider from menu (not first launch)
    func showAddProviderFromMenu() {
        isFirstLaunchProviderSetup = false
        showAddProvider = true
    }
}
