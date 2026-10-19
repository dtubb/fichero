#if canImport(AppKit)
import FicheroAPIClient
import SwiftUI

struct MacRemoteClientPairingSection: View {
    @Bindable private var appState: AppState
    @Bindable private var backendService: EmbeddedBackendService
    @Bindable private var libraryManager: LibraryManager
    @AppStorage(EngineConfig.userDefaultsKey) private var engineHost = EngineConfig.defaultHostString

    @State private var clientInvite = ""
    @State private var clientPairingError: String?
    @State private var isClientPairing = false
    @State private var showingManualInvite = false
    // Shown only after the host answers "person required": a Multi-user host asks who this Mac is.
    @State private var needsPerson = false
    @State private var personName = ""
    @State private var personPassword = ""

    init(
        appState: AppState,
        backendService: EmbeddedBackendService,
        libraryManager: LibraryManager
    ) {
        self._appState = Bindable(wrappedValue: appState)
        self._backendService = Bindable(wrappedValue: backendService)
        self._libraryManager = Bindable(wrappedValue: libraryManager)
    }

    var body: some View {
        Section("Connect This Mac to Another Fichero") {
            Text("Paste the invite link from the host Mac.")
                .font(.caption)
                .foregroundStyle(.secondary)

            DisclosureGroup("Invite link", isExpanded: $showingManualInvite) {
                VStack(alignment: .leading, spacing: 12) {
                    TextField("Invite link", text: $clientInvite, axis: .vertical)
                        .textFieldStyle(.roundedBorder)
                        .autocorrectionDisabled()

                    if let host = inviteHost {
                        Text("Connects to \(host)")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }

                    if needsPerson {
                        Text("This library uses Multi-user. Sign in as the person using this Mac.")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        TextField("Username", text: $personName)
                            .textFieldStyle(.roundedBorder)
                            .autocorrectionDisabled()
                        SecureField("Password", text: $personPassword)
                            .textFieldStyle(.roundedBorder)
                    }

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
            // A tapped fichero:// link lands here (#3788): prefill it and open the
            // drawer so the user SEES what they are about to connect to and presses
            // Connect themselves. Never pair silently — it repoints this Mac at a
            // remote host. Consumed once, so re-opening Settings doesn't re-fill it.
            .onChange(of: appState.pendingPairingInvite) { _, invite in
                guard let invite, !invite.isEmpty else { return }
                clientInvite = invite
                showingManualInvite = true
                appState.pendingPairingInvite = nil
            }
            .task {
                // The link may have arrived BEFORE this view existed (the app was
                // launched by the link). onChange would never fire for that.
                if let invite = appState.pendingPairingInvite, !invite.isEmpty {
                    clientInvite = invite
                    showingManualInvite = true
                    appState.pendingPairingInvite = nil
                }
            }

            if let clientPairingError {
                Label(clientPairingError, systemImage: "exclamationmark.triangle")
                    .font(.caption)
                    .foregroundStyle(.orange)
            }
        }
    }

    /// The host the pasted invite points at, shown read-only so the person sees where they are about to connect.
    private var inviteHost: String? {
        (try? RemoteClientPairing.pairingFields(fromInviteOrPayload: clientInvite))
            .flatMap { URL(string: $0.remoteURL)?.host }
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
                expectedSPKIPin: pairingFields.spkiPin,
                person: PairingPerson(username: personName, password: personPassword)
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
            if error as? RemoteClientPairingError == .personRequired { needsPerson = true }
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
/// pairing UI; dismissing ("Use Local Server") keeps the already-running
/// embedded engine. Co-located with the section it presents (the app target
/// uses explicit file references, so a standalone file would need a project
/// edit for no behavioural gain).
struct RemoteConnectionChooserSheet: View {
    @Bindable private var appState: AppState
    @Bindable private var backendService: EmbeddedBackendService
    @Bindable private var libraryManager: LibraryManager
    @Environment(\.dismiss) private var dismiss

    init(
        appState: AppState,
        backendService: EmbeddedBackendService,
        libraryManager: LibraryManager
    ) {
        self._appState = Bindable(wrappedValue: appState)
        self._backendService = Bindable(wrappedValue: backendService)
        self._libraryManager = Bindable(wrappedValue: libraryManager)
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
                Button("Use Local Server") { dismiss() }
                    .keyboardShortcut(.cancelAction)
            }
            .padding()
        }
        .frame(minWidth: 460, minHeight: 380)
    }
}
#endif
