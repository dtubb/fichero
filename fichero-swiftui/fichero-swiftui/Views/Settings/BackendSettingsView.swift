import SwiftUI

// MARK: - Backend Settings

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
