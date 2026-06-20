#if canImport(AppKit)
import AppKit
import FicheroAPIClient
import SwiftUI

struct MacRemoteClientPairingSection: View {
    @EnvironmentObject private var appState: AppState
    @EnvironmentObject private var backendService: EmbeddedBackendService
    @EnvironmentObject private var libraryManager: LibraryManager
    @AppStorage(EngineConfig.userDefaultsKey) private var engineHost = EngineConfig.defaultHostString

    @State private var clientInvite = ""
    @State private var clientPairingError: String?
    @State private var isClientPairing = false
    @State private var showingManualInvite = false

    var body: some View {
        Section("Connect This Mac to Another Fichero") {
            Text("Scan the QR code shown on the host Mac.")
                .font(.caption)
                .foregroundStyle(.secondary)

            DisclosureGroup("Manual link", isExpanded: $showingManualInvite) {
                VStack(alignment: .leading, spacing: 12) {
                    Text("Use this only if the camera is unavailable.")
                        .font(.caption)
                        .foregroundStyle(.secondary)

                    TextField("Invite link or QR text", text: $clientInvite, axis: .vertical)
                        .textFieldStyle(.roundedBorder)
                        .autocorrectionDisabled()

                    HStack {
                        Button("Paste Link") {
                            pasteInviteFromClipboard()
                        }
                        .buttonStyle(.bordered)

                        Button(isClientPairing ? "Connecting…" : "Connect This Mac") {
                            Task { await connectThisMacAsRemoteClient() }
                        }
                        .buttonStyle(.borderedProminent)
                        .disabled(isClientPairing || clientInvite.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                    }
                }
                .padding(.top, 6)
            }

            if let clientPairingError {
                Text(clientPairingError)
                    .font(.caption)
                    .foregroundStyle(.red)
            }
        }
    }

    private func pasteInviteFromClipboard() {
        if let pasted = NSPasteboard.general.string(forType: .string) {
            clientInvite = pasted
            clientPairingError = nil
        }
    }

    private func connectThisMacAsRemoteClient() async {
        isClientPairing = true
        clientPairingError = nil
        defer { isClientPairing = false }

        let previousHost = engineHost
        do {
            let pairingFields = try RemoteClientPairing.pairingFields(fromInviteOrPayload: clientInvite)
            let result = try await RemoteClientPairing.pairDevice(
                remoteURL: pairingFields.remoteURL,
                pairCode: pairingFields.pairCode,
                deviceName: RemoteClientPairing.defaultDeviceName(),
                expectedSPKIPin: pairingFields.spkiPin
            )
            try await RemoteClientPairing.probeRemoteHealth(at: result.apiRoot, expectedSPKIPin: pairingFields.spkiPin)
            try RemoteClientPairing.persistPairedHost(result, expectedSPKIPin: pairingFields.spkiPin)
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
                RemoteClientPairing.rollbackFailedHostSwitch(
                    previousHost: previousHost,
                    attemptedHost: result.apiRoot
                )
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
