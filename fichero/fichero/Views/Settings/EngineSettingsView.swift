#if canImport(AppKit)
import SwiftUI

struct EngineSettingsView: View {
    @EnvironmentObject var appState: AppState
    @EnvironmentObject var backendService: EmbeddedBackendService
    @EnvironmentObject var libraryManager: LibraryManager
    // Default OFF to match EngineConfig.multiuserEnabled (absent key ⇒ off);
    // a `true` default would show the toggle on while the engine ran single-user.
    @AppStorage(EngineConfig.multiuserEnabledKey) private var multiuserEnabled = false

    @State private var storageStats: StorageStats?
    @State private var isLoadingStats = false
    @State private var isRestarting = false
    @State private var restartError: String?

    var body: some View {
        Form {
            Section {
                LabeledContent("Status") {
                    HStack(spacing: 6) {
                        Circle()
                            .fill(appState.isBackendRunning ? Color.green : Color.red)
                            .frame(width: 8, height: 8)
                        Text(appState.isBackendRunning ? "Running" : "Stopped")
                    }
                }

                LabeledContent("Library") {
                    HStack {
                        Text(libraryDescription)
                            .foregroundStyle(.secondary)
                        Spacer()
                        Button(isRestarting ? "Restarting…" : "Restart") {
                            Task { await restartEngine() }
                        }
                        .disabled(isRestarting || !EngineConfig.engineIsLocal)
                    }
                }

                LabeledContent("Multi-user mode") {
                    Toggle("", isOn: $multiuserEnabled)
                        .labelsHidden()
                }

                Text(multiuserStatusDescription)
                    .font(.caption)
                    .foregroundStyle(.secondary)

                if isLoadingStats {
                    LabeledContent("Storage") {
                        ProgressView().controlSize(.small)
                    }
                } else if let stats = storageStats {
                    LabeledContent("Storage") {
                        Text(ByteCountFormatter.string(fromByteCount: stats.totalSize, countStyle: .file))
                            .foregroundStyle(.secondary)
                    }
                }
            } footer: {
                if let restartError {
                    Text(restartError).foregroundStyle(.red).font(.caption)
                } else {
                    Text("Fichero's engine indexes, searches, transcribes, and runs workflows for this library.")
                        .font(.caption)
                }
            }
        }
        .formStyle(.grouped)
        .task { await loadStorageStats() }
    }

    private var libraryDescription: String {
        EngineConfig.requiresExternalBackendConnection
            ? "Connected to a shared Fichero library."
            : "Local engine for this Mac."
    }

    private var multiuserStatusDescription: String {
        if appState.isBackendRunning {
            return multiuserEnabled
                ? "Backend is enforcing per-library authz."
                : "Backend is not enforcing per-library authz."
        }

        return multiuserEnabled
            ? "Backend will enforce per-library authz the next time it starts."
            : "Backend will run without per-library authz until you turn this back on."
    }

    private func restartEngine() async {
        isRestarting = true
        restartError = nil
        defer { isRestarting = false }
        backendService.stop()
        do {
            try await backendService.start()
            await appState.checkBackendHealth()
            appState.reconfigureGeneratedClientsForCurrentHost()
            libraryManager.reconfigureGeneratedClientsForCurrentHost()
        } catch {
            restartError = error.localizedDescription
        }
    }

    private func loadStorageStats() async {
        isLoadingStats = true
        defer { isLoadingStats = false }
        guard let storageService = libraryManager.globalLibrary?.storageService else { return }
        storageStats = try? await storageService.getStats()
    }
}
#endif
