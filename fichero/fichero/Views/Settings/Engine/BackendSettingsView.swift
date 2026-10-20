import SwiftUI

// MARK: - Backend Settings

// Backend connection settings
struct BackendSettingsView: View {
    @Environment(AppState.self) var appState
    @Environment(EmbeddedBackendService.self) var backendService
    // storageService is per-LIBRARY, not in the Settings scene environment — reach it
    // optionally via libraryManager (which IS injected here). A required @EnvironmentObject
    // would trap "No ObservableObject of type StorageService" and crash this tab.
    @Environment(LibraryManager.self) var libraryManager
    @AppStorage(EngineConfig.userDefaultsKey) private var engineHost = EngineConfig.defaultHostString

    @State private var storageStats: StorageStats?
    @State private var isLoadingStats = false
    @State private var statsError: String?

    var body: some View {
        Form {
            Section {
                HStack(alignment: .center, spacing: 12) {
                    Circle()
                        .fill(appState.isBackendRunning ? Color.green : Color.red)
                        .frame(width: 10, height: 10)

                    VStack(alignment: .leading, spacing: 4) {
                        Text(appState.isBackendRunning ? "Connected" : "Disconnected")
                            .font(.headline)
                        Text(connectionDescription)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
            }

            Section("Statistics") {
                LabeledContent("Documents") {
                    Text("\(appState.documentCount)")
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

            AdvancedConnectionSection(
                engineHost: $engineHost,
                appState: appState,
                backendService: backendService,
                libraryManager: libraryManager
            )
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
        guard let storageService = libraryManager.globalLibrary?.storageService else {
            // No library open → no per-library storage stats to show.
            storageStats = nil
            return
        }
        do {
            storageStats = try await storageService.getStats()
        } catch {
            statsError = error.localizedDescription
        }
    }

    private var connectionDescription: String {
        if appState.isBackendRunning {
            return EngineConfig.requiresExternalBackendConnection
                ? "This Mac is connected to another Fichero project."
                : "Fichero is running on this Mac."
        }
        return EngineConfig.requiresExternalBackendConnection
            ? "Check the shared project link in Advanced if this Mac should reconnect."
            : "Start the project on this Mac to share it with other devices."
    }

}

private struct AdvancedConnectionSection: View {
    /// The stored host. Written only by `EngineHostSwitch` (#5916); the field below edits a draft.
    @Binding var engineHost: String
    let appState: AppState
    let backendService: EmbeddedBackendService
    let libraryManager: LibraryManager

    @State private var draft = ""
    @State private var isApplying = false
    @State private var applyError: String?

    var body: some View {
        Section {
            DisclosureGroup("Advanced") {
                TextField("Server URL", text: $draft)
                    .textFieldStyle(.roundedBorder)
                    .autocorrectionDisabled()

                LabeledContent("Effective API Base") {
                    Text(EngineConfig.apiBaseURL.absoluteString)
                        .foregroundStyle(.secondary)
                        .textSelection(.enabled)
                }

                if hostIsInvalid {
                    Text("Invalid URL")
                        .font(.caption)
                        .foregroundStyle(.red)
                }

                Button("Apply") { Task { await apply() } }
                    .disabled(hostIsInvalid || isApplying)

                if let applyError {
                    Text(applyError)
                        .font(.caption)
                        .foregroundStyle(.red)
                }

                Text("Leave blank only when this Mac should use its embedded local server.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .onAppear { draft = engineHost }
        .onChange(of: engineHost) { _, stored in draft = stored }
    }

    /// Same stop, write, repoint, start, check and roll-back as Connect This Mac, through the one procedure (#5916).
    private func apply() async {
        isApplying = true
        applyError = nil
        defer { isApplying = false }
        do {
            try await EngineHostSwitch.standard(
                appState: appState, backendService: backendService, libraryManager: libraryManager,
                setHost: { engineHost = $0 }
            ).run(
                from: engineHost, to: draft,
                notResponding: draft == engineHost
                    ? "The engine did not answer."
                    : "That address did not answer, so the previous one is back.")
        } catch {
            applyError = error.localizedDescription
        }
        draft = engineHost
    }

    private var hostIsInvalid: Bool {
        if case .invalid = EngineConfig.hostConfiguration(from: draft) {
            return true
        }
        return false
    }
}
