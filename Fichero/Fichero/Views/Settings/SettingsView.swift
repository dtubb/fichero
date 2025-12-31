import SwiftUI

/// Main settings view with tabs for General and Backend
struct SettingsView: View {
    @EnvironmentObject var appState: AppState

    var body: some View {
        TabView {
            GeneralSettingsView()
                .tabItem {
                    Label("General", systemImage: "gear")
                }

            BackendSettingsView()
                .tabItem {
                    Label("Backend", systemImage: "server.rack")
                }
        }
        .frame(width: 550, height: 400)
    }
}

/// General application settings
struct GeneralSettingsView: View {
    @AppStorage("thumbnailSize") private var thumbnailSize: Double = 120
    @AppStorage("autoExtractText") private var autoExtractText: Bool = true
    @AppStorage("autoCreateEmbeddings") private var autoCreateEmbeddings: Bool = true

    var body: some View {
        Form {
            Section("Display") {
                Slider(value: $thumbnailSize, in: 80...200) {
                    Text("Thumbnail Size")
                }
            }

            Section("Ingestion") {
                Toggle("Auto-extract text from documents", isOn: $autoExtractText)
                Toggle("Auto-create search embeddings", isOn: $autoCreateEmbeddings)
            }
        }
        .padding()
    }
}

/// Backend connection settings
struct BackendSettingsView: View {
    @EnvironmentObject var appState: AppState
    @AppStorage("backendPort") private var backendPort: Int = 8765
    @AppStorage("backendHost") private var backendHost: String = "127.0.0.1"

    var body: some View {
        Form {
            Section("Connection") {
                TextField("Host", text: $backendHost)
                TextField("Port", value: $backendPort, format: .number)

                HStack {
                    Circle()
                        .fill(appState.isBackendRunning ? Color.green : Color.red)
                        .frame(width: 10, height: 10)

                    Text(appState.isBackendRunning ? "Connected" : "Disconnected")

                    Spacer()

                    if !appState.isBackendRunning {
                        Button("Start Backend") {
                            Task { await appState.startBackend() }
                        }
                    }
                }
            }

            Section("Statistics") {
                LabeledContent("Documents") {
                    Text("\(appState.documentCount)")
                }
                LabeledContent("Indexed") {
                    Text("\(appState.indexedCount)")
                }
            }
        }
        .padding()
    }
}
