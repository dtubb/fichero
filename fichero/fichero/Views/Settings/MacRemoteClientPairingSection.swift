#if canImport(AppKit)
import SwiftUI

struct MacRemoteClientPairingSection: View {
    @EnvironmentObject private var appState: AppState
    @EnvironmentObject private var backendService: EmbeddedBackendService
    @EnvironmentObject private var libraryManager: LibraryManager
    @AppStorage(EngineConfig.userDefaultsKey) private var engineHost = EngineConfig.defaultHostString

    @State private var clientPairingPayload = ""
    @State private var clientRemoteURL = EngineConfig.usesCustomHost ? EngineConfig.hostString : ""
    @State private var clientPairCode = ""
    @State private var clientDeviceName = RemoteClientPairing.defaultDeviceName()
    @State private var clientPairingError: String?
    @State private var isClientPairing = false

    var body: some View {
        Section("Join Remote Host") {
            Text(
                "Use the pairing URL and code from another Mac to make this Mac a remote client. "
                    + "This stores a host-scoped device token and switches the app away from localhost."
            )
            .font(.caption)
            .foregroundStyle(.secondary)

            TextField("Pairing Payload (optional)", text: $clientPairingPayload)
                .textFieldStyle(.roundedBorder)
                .autocorrectionDisabled()

            Button("Apply Pairing Payload") {
                applyClientPairingPayload()
            }
            .disabled(clientPairingPayload.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)

            TextField("Remote URL", text: $clientRemoteURL)
                .textFieldStyle(.roundedBorder)
                .autocorrectionDisabled()

            TextField("Pairing Code", text: $clientPairCode)
                .textFieldStyle(.roundedBorder)
                .autocorrectionDisabled()

            TextField("Device Name", text: $clientDeviceName)
                .textFieldStyle(.roundedBorder)
                .autocorrectionDisabled()

            HStack {
                Button(isClientPairing ? "Connecting..." : "Connect This Mac") {
                    Task { await connectThisMacAsRemoteClient() }
                }
                .disabled(isClientPairing)

                Button("Use Current Remote Host") {
                    clientRemoteURL = EngineConfig.hostString
                }
                .disabled(EngineConfig.engineIsLocal || isClientPairing)
            }

            if let clientPairingError {
                Text(clientPairingError)
                    .font(.caption)
                    .foregroundStyle(.red)
            }
        }
    }

    private func applyClientPairingPayload() {
        do {
            let pairingFields = try RemoteClientPairing.pairingFields(from: clientPairingPayload)
            clientRemoteURL = pairingFields.remoteURL
            clientPairCode = pairingFields.pairCode
            clientPairingError = nil
        } catch {
            clientPairingError = error.localizedDescription
        }
    }

    private func connectThisMacAsRemoteClient() async {
        isClientPairing = true
        clientPairingError = nil
        defer { isClientPairing = false }

        let previousHost = engineHost
        do {
            let result = try await RemoteClientPairing.pairDevice(
                remoteURL: clientRemoteURL,
                pairCode: clientPairCode,
                deviceName: clientDeviceName
            )
            try await RemoteClientPairing.probeRemoteHealth(at: result.apiRoot)
            try RemoteClientPairing.persistPairedHost(result)
            backendService.stop()
            engineHost = result.apiRoot.absoluteString
            appState.reconfigureGeneratedClientsForCurrentHost()
            libraryManager.reconfigureGeneratedClientsForCurrentHost()
            do {
                try await backendService.start()
                await reconnectToConfiguredRemoteHost()
                if !appState.isBackendRunning {
                    throw APIError.badRequest("Paired successfully, but the verified remote host is not responding now.")
                }
            } catch {
                await restorePreviousHost(previousHost)
                throw error
            }
        } catch {
            clientPairingError = error.localizedDescription
        }
    }

    private func reconnectToConfiguredRemoteHost() async {
        await appState.checkBackendHealth()
        guard appState.isBackendRunning else {
            backendService.status = .failed
            backendService.errorMessage = appState.backendError
            return
        }

        backendService.status = .running
        backendService.errorMessage = nil
        appState.startBackendHeartbeat()
        await KnownLibraryRegistryStore.shared.refresh()
        await libraryManager.backendDidBecomeReady()
    }

    private func restorePreviousHost(_ previousHost: String) async {
        backendService.stop()
        engineHost = previousHost
        appState.reconfigureGeneratedClientsForCurrentHost()
        libraryManager.reconfigureGeneratedClientsForCurrentHost()

        do {
            try await backendService.start()
            await reconnectToConfiguredRemoteHost()
        } catch {
            backendService.status = .failed
            backendService.errorMessage = error.localizedDescription
        }
    }
}
#endif
