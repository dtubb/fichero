#if canImport(AppKit)
import SwiftUI

struct EngineSettingsView: View {
    @Environment(AppState.self) var appState
    @Environment(EmbeddedBackendService.self) var backendService
    @Environment(LibraryManager.self) var libraryManager
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
                    Toggle("", isOn: multiuserBinding)
                        .labelsHidden()
                        // Only the Mac hosting the library can change its multi-user
                        // mode (the engine reads the flag at startup and we restart it
                        // to apply). On a remote-connected Mac the switch would write a
                        // local flag the host never sees — a silent no-op — so disable
                        // it there instead of offering a dead control (#3776).
                        .disabled(isRestarting || !EngineConfig.engineIsLocal)
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
        .task {
            // Refresh the engine's real multi-user state (single source of truth,
            // #3331) and align the desired toggle to it so the control reflects
            // reality on open; an explicit toggle afterward is a pending change.
            await appState.identityStore.load()
            multiuserEnabled = appState.identityStore.multiuserEnabled
            await loadStorageStats()
        }
    }

    private var libraryDescription: String {
        EngineConfig.requiresExternalBackendConnection
            ? "Connected to a shared Fichero library."
            : "Local engine for this Mac."
    }

    /// The engine's ACTUAL multi-user state — the single source of truth
    /// (`GET /api/auth/identity` via IdentityStore), shared with the Users and
    /// Connect tabs so all three agree (#3331). The @AppStorage flag is only the
    /// desired setting the toggle writes, applied on the next engine restart.
    private var backendMultiuser: Bool { appState.identityStore.multiuserEnabled }

    /// Flipping multi-user is ONE action. The engine reads this flag at startup, so
    /// the app restarts its OWN engine to apply the change — the user does not press
    /// a separate "Restart" to finish our lifecycle management (#3776). Off by
    /// default; this does not make multi-user always-on and the engine's fail-closed
    /// enforcement is unchanged. The `.task` alignment writes `multiuserEnabled`
    /// directly, bypassing this setter, so opening Settings never restarts.
    private var multiuserBinding: Binding<Bool> {
        Binding(
            get: { multiuserEnabled },
            set: { newValue in
                multiuserEnabled = newValue
                // No-op if the engine already reflects the desired state.
                guard newValue != backendMultiuser else { return }
                Task { await restartEngine() }
            }
        )
    }

    private var multiuserStatusDescription: String {
        guard appState.isBackendRunning else {
            return multiuserEnabled
                ? "Multi-user will be enforced when the engine starts."
                : "The engine runs without multi-user."
        }
        // The toggle applies itself by restarting, so there is no "please restart"
        // instruction to give — just report what the engine is doing now.
        return backendMultiuser
            ? "The engine is enforcing per-library access."
            : "The engine is not enforcing per-library access."
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
            // Re-read the engine's real multi-user state so the status line and the
            // toggle reflect what the restarted engine is actually enforcing (#3331).
            await appState.identityStore.load()
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
