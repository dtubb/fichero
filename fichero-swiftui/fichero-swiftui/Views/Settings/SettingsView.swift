import SwiftUI

// MARK: - Settings View

/// Main settings view with tabs for General, AI, Backend, and Models
struct SettingsView: View {
    @EnvironmentObject var appState: AppState

    var body: some View {
        TabView {
            GeneralSettingsView()
                .tabItem {
                    Label("General", systemImage: "gear")
                }

            AISettingsView()
                .tabItem {
                    Label("AI", systemImage: "brain")
                }

            BackendSettingsView()
                .tabItem {
                    Label("Backend", systemImage: "server.rack")
                }

            LocalModelsSettingsView()
                .tabItem {
                    Label("Models", systemImage: "arrow.down.circle")
                }
        }
        .frame(width: 550, height: 450)
    }
}
