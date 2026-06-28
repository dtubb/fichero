#if canImport(AppKit)
import FicheroAPIClient
import SwiftUI

struct MacRemoteClientPairingSection: View {
    @ObservedObject private var appState: AppState
    @ObservedObject private var backendService: EmbeddedBackendService
    @ObservedObject private var libraryManager: LibraryManager
    @AppStorage(EngineConfig.userDefaultsKey) private var engineHost = EngineConfig.defaultHostString

    @State private var clientInvite = ""
    @State private var clientPairingError: String?
    @State private var isClientPairing = false
    @State private var showingManualInvite = false

    init(
        appState: AppState,
        backendService: EmbeddedBackendService,
        libraryManager: LibraryManager
    ) {
        self._appState = ObservedObject(wrappedValue: appState)
        self._backendService = ObservedObject(wrappedValue: backendService)
        self._libraryManager = ObservedObject(wrappedValue: libraryManager)
    }

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
        if let pasted = PlatformPasteboard.string() {
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
            try RemoteClientPairing.persistPairedHost(
                result,
                expectedSPKIPin: pairingFields.spkiPin,
                libraryPath: pairingFields.libraryPath
            )
            backendService.stop()
            engineHost = result.apiRoot.absoluteString
            libraryManager.adoptPairedRemoteLibrary()
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
        libraryManager.adoptPairedRemoteLibrary()
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

/// Remote-client connection chooser, presented at launch when the user holds
/// Option (#2381).
///
/// A normal Mac launch uses the embedded local engine, so the backend URL /
/// pairing fields no longer need to live in regular Settings. Holding Option
/// surfaces this explicit flow to connect *this* Mac to another Fichero host.
/// It reuses `MacRemoteClientPairingSection` rather than duplicating the
/// pairing UI; dismissing ("Use Local Engine") keeps the already-running
/// embedded engine. Co-located with the section it presents (the app target
/// uses explicit file references, so a standalone file would need a project
/// edit for no behavioural gain).
struct RemoteConnectionChooserSheet: View {
    @ObservedObject private var appState: AppState
    @ObservedObject private var backendService: EmbeddedBackendService
    @ObservedObject private var libraryManager: LibraryManager
    @Environment(\.dismiss) private var dismiss

    init(
        appState: AppState,
        backendService: EmbeddedBackendService,
        libraryManager: LibraryManager
    ) {
        self._appState = ObservedObject(wrappedValue: appState)
        self._backendService = ObservedObject(wrappedValue: backendService)
        self._libraryManager = ObservedObject(wrappedValue: libraryManager)
    }

    var body: some View {
        VStack(spacing: 0) {
            Form {
                MacRemoteClientPairingSection(
                    appState: appState,
                    backendService: backendService,
                    libraryManager: libraryManager
                )
            }
            .formStyle(.grouped)

            Divider()

            HStack {
                Spacer()
                Button("Use Local Engine") { dismiss() }
                    .keyboardShortcut(.cancelAction)
            }
            .padding()
        }
        .frame(minWidth: 460, minHeight: 380)
    }
}
#endif
