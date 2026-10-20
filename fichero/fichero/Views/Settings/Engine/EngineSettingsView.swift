#if canImport(AppKit)
import SwiftUI

/// Settings › Server (`sharing.settings.three-panes`, #5928): the engine's status with its one button, its storage, and a
/// collapsed Advanced for a hand-run engine's address and who has connected. Nothing else.
struct EngineSettingsView: View {
    @Environment(AppState.self) var appState
    @Environment(EmbeddedBackendService.self) var backendService
    @Environment(LibraryManager.self) var libraryManager
    @AppStorage(EngineConfig.userDefaultsKey) private var engineHost = EngineConfig.defaultHostString

    @State private var storageStats: StorageStats?
    @State private var isRestarting = false
    @State private var restartError: String?
    @State private var advanced = ServerAdvancedModel()
    @State private var clients: [String] = []

    var body: some View {
        Form {
            Section {
                LabeledContent("Status") {
                    HStack(spacing: 8) {
                        Circle()
                            .fill(appState.isBackendRunning ? Color.green : Color.red)
                            .frame(width: 8, height: 8)
                        Text(ServerSettingsText.status(running: appState.isBackendRunning))
                        Button(isRestarting ? "Restarting…" : "Restart") {
                            Task { await restartEngine() }
                        }
                        .disabled(!ServerSettingsText.canRestart(isRestarting: isRestarting, engineIsLocal: EngineConfig.engineIsLocal))
                    }
                }
                if let stats = storageStats {
                    LabeledContent("Storage") {
                        Text(ByteCountFormatter.string(fromByteCount: stats.totalSize, countStyle: .file))
                            .foregroundStyle(.secondary)
                    }
                }
                if let restartError {
                    Text(restartError).foregroundStyle(.red).font(.caption)
                }
            }
            Section {
                DisclosureGroup("Advanced") {
                    TextField("Server URL", text: $advanced.draft, prompt: Text("Built-in"))
                        .textFieldStyle(.roundedBorder)
                        .autocorrectionDisabled()
                        .onSubmit { Task { await applyServerURL() } }
                    if let problem = advanced.problem {
                        Text(problem).font(.caption).foregroundStyle(.red)
                    } else if let error = advanced.error {
                        Text(error).font(.caption).foregroundStyle(.red)
                    }
                    if let line = ServerSettingsText.clientsLine(clients) {
                        LabeledContent("Clients") { Text(line).foregroundStyle(.secondary) }
                    }
                }
            }
        }
        .formStyle(.grouped)
        .onAppear { advanced.sync(stored: engineHost) }
        .onChange(of: engineHost) { _, stored in advanced.sync(stored: stored) }
        .task {
            await appState.identityStore.load()
            await loadStorageStats()
            await loadClients()
        }
    }

    /// Return commits: the same stop, write, repoint, start, check and roll-back as Connect to Another Mac (#5916).
    private func applyServerURL() async {
        await advanced.commit(stored: engineHost) { from, to, notResponding in
            try await EngineHostSwitch.standard(
                appState: appState, backendService: backendService, libraryManager: libraryManager,
                setHost: { engineHost = $0 }
            ).run(from: from, to: to, notResponding: notResponding)
        }
        advanced.sync(stored: engineHost)
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
            await appState.identityStore.load()
        } catch {
            restartError = error.localizedDescription
        }
    }

    private func loadStorageStats() async {
        guard let storageService = libraryManager.globalLibrary?.storageService else { return }
        storageStats = try? await storageService.getStats()
    }

    private func loadClients() async {
        let records = (try? await PairingService(apiRoot: EngineConfig.host).connectedClients()) ?? []
        clients = records.map(\.client)
    }
}
#endif
