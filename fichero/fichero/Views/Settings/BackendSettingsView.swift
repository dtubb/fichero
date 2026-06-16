import SwiftUI

// MARK: - Backend Settings

/// Backend connection settings
struct BackendSettingsView: View {
    @EnvironmentObject var appState: AppState
    @EnvironmentObject var storageService: StorageServiceGenerated
    @AppStorage(EngineConfig.userDefaultsKey) private var engineHost = EngineConfig.defaultHostString

    @State private var storageStats: StorageStats?
    @State private var isLoadingStats = false
    @State private var statsError: String?

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

                if isLoadingStats {
                    LabeledContent("Storage") {
                        ProgressView()
                            .controlSize(.small)
                    }
                } else if let error = statsError {
                    LabeledContent("Storage") {
                        Text(error)
                            .foregroundStyle(.red)
                            .font(.caption)
                    }
                } else if let stats = storageStats {
                    LabeledContent("Total Size") {
                        Text(ByteCountFormatter.string(fromByteCount: stats.totalSize, countStyle: .file))
                    }
                    LabeledContent("Files") {
                        Text("\(stats.fileCount)")
                    }
                    LabeledContent("Collections") {
                        Text("\(stats.collectionCount)")
                    }
                    LabeledContent("Linked Files") {
                        Text("\(stats.linkedCount)")
                    }
                    LabeledContent("Copied Files") {
                        Text("\(stats.copiedCount)")
                    }
                }
            }
        }
        .formStyle(.grouped)
        .task {
            await loadStorageStats()
        }
    }

    // MARK: - Private

    private func loadStorageStats() async {
        isLoadingStats = true
        statsError = nil
        defer { isLoadingStats = false }
        do {
            storageStats = try await storageService.getStats()
        } catch {
            statsError = error.localizedDescription
        }
    }
}
