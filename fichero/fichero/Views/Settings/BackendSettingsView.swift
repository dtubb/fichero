import SwiftUI

// MARK: - Backend Settings

// Backend connection settings
struct BackendSettingsView: View {
    @Environment(AppState.self) var appState
    @Environment(EmbeddedBackendService.self) var backendService
    // storageService is per-LIBRARY, not in the Settings scene environment — reach it
    // optionally via libraryManager (which IS injected here). A required @EnvironmentObject
    // would trap "No ObservableObject of type StorageServiceGenerated" and crash this tab.
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

            // Joining ANOTHER Mac's library — the client side of pairing, which is a
            // different question from sharing this one, and stays here.
            //
            // Sharing THIS Mac used to be duplicated here too ("Share This Mac"), in
            // parallel with Settings → Library Access → Devices: two surfaces, two
            // toggles over the same keys, two device lists, two sets of reasons the
            // QR could vanish. There is now one (#3777) — ShareSettingsView.
            #if canImport(AppKit)
            MacRemoteClientPairingSection(
                appState: appState,
                backendService: backendService,
                libraryManager: libraryManager
            )
            #endif

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

            AdvancedConnectionSection(
                engineHost: $engineHost,
                appState: appState,
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
                ? "This Mac is connected to another Fichero library."
                : "Fichero is running on this Mac."
        }
        return EngineConfig.requiresExternalBackendConnection
            ? "Check the shared library link in Advanced if this Mac should reconnect."
            : "Start the library on this Mac to share it with other devices."
    }

}

private struct AdvancedConnectionSection: View {
    @Binding var engineHost: String
    let appState: AppState
    let libraryManager: LibraryManager

    var body: some View {
        Section {
            DisclosureGroup("Advanced") {
                TextField("Engine URL", text: $engineHost)
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

                Button("Apply") {
                    appState.reconfigureGeneratedClientsForCurrentHost()
                    libraryManager.reconfigureGeneratedClientsForCurrentHost()
                }
                .disabled(hostIsInvalid)

                Text("Leave blank only when this Mac should use its embedded local engine.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
    }

    private var hostIsInvalid: Bool {
        if case .invalid = EngineConfig.hostConfiguration(from: engineHost) {
            return true
        }
        return false
    }
}
