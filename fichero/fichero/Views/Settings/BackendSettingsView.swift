import SwiftUI

// MARK: - Backend Settings

/// Backend connection settings
struct BackendSettingsView: View {
    @EnvironmentObject var appState: AppState
    @AppStorage(EngineConfig.userDefaultsKey) private var engineHost = EngineConfig.defaultHostString

    var body: some View {
        Form {
            Section("Connection") {
                TextField("Engine URL", text: $engineHost)
                    .textFieldStyle(.roundedBorder)
                    .autocorrectionDisabled()

                LabeledContent("Effective API Base") {
                    Text(EngineConfig.apiBaseURL.absoluteString)
                        .foregroundStyle(.secondary)
                        .textSelection(.enabled)
                }

                Text("Leave blank to use the embedded localhost engine.")
                    .font(.caption)
                    .foregroundStyle(.secondary)

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
        .formStyle(.grouped)
    }
}
