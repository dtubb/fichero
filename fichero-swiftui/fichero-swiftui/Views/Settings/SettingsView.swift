import SwiftUI

// MARK: - Settings View

/// Main settings view with tabs for General, AI, Backend, and Models
struct SettingsView: View {
    @EnvironmentObject var appState: AppState
    @ObservedObject var featureManager = FeatureManager.shared

    var body: some View {
        TabView {
            AISettingsView()
                .tabItem {
                    Label("Defaults", systemImage: "brain")
                }

            if featureManager.isSettingsGeneralTabEnabled {
                GeneralSettingsView()
                    .tabItem {
                        Label("General", systemImage: "gear")
                    }
            }

            if featureManager.isSettingsBackendTabEnabled {
                BackendSettingsView()
                    .tabItem {
                        Label("Backend", systemImage: "server.rack")
                    }
            }

            if featureManager.isSettingsModelsTabEnabled {
                LocalModelsSettingsView()
                    .tabItem {
                        Label("Models", systemImage: "arrow.down.circle")
                    }
            }
        }
        .frame(width: 550, height: 450)
    }
}
