#if canImport(AppKit)
import FicheroAPIClient
import SwiftUI

struct MacRemoteClientPairingSection: View {
    @Bindable private var appState: AppState
    @Bindable private var backendService: EmbeddedBackendService
    @Bindable private var libraryManager: LibraryManager
    @AppStorage(EngineConfig.userDefaultsKey) private var engineHost = EngineConfig.defaultHostString

    @State private var clientInvite = ""
    // The Macs nearby (#5892): Bonjour browsing, this Mac left out; picking one starts pairing with it.
    @State private var nearby = NearbyHosts()
    @State private var chosen: HostChoices.Found?
    @State private var pairCode = ""
    @State private var clientPairingError: String?
    @State private var isClientPairing = false
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
            nearbyList

            Text(chosenNeedsCodeOnly
                 ? "Type the pairing code shown on \(chosen?.name ?? "the host Mac")."
                 : "Paste the invite link from the host Mac.")
                .font(.caption)
                .foregroundStyle(.secondary)

            VStack(alignment: .leading, spacing: 12) {
                if chosenNeedsCodeOnly {
                    TextField("Pairing code", text: $pairCode)
                        .textFieldStyle(.roundedBorder)
                        .autocorrectionDisabled()
                } else {
                    TextField("Invite link", text: $clientInvite, axis: .vertical)
                        .textFieldStyle(.roundedBorder)
                        .autocorrectionDisabled()
                }

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
                    .disabled(isClientPairing || (chosenNeedsCodeOnly ? pairCode : clientInvite)
                        .trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                }
            }
            // A tapped fichero:// link lands here (#3788): prefill it so the
            // user SEES what they are about to connect to and presses
            // Connect themselves. Never pair silently — it repoints this Mac at a
            // remote host. Consumed once, so re-opening Settings doesn't re-fill it.
            .onChange(of: appState.pendingPairingInvite) { _, invite in
                guard let invite, !invite.isEmpty else { return }
                clientInvite = invite
                appState.pendingPairingInvite = nil
            }
            .task {
                nearby.start()
                // The link may have arrived BEFORE this view existed (the app was
                // launched by the link). onChange would never fire for that.
                if let invite = appState.pendingPairingInvite, !invite.isEmpty {
                    clientInvite = invite
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

    /// The Fichero Macs nearby, this Mac left out; picking one starts pairing with it (#5892).
    @ViewBuilder private var nearbyList: some View {
        let hosts = HostChoices.offered(
            nearby.found, ownName: HostChoices.ownServiceName(hostName: ProcessInfo.processInfo.hostName))
        if hosts.isEmpty {
            Text("No other Fichero found nearby. Paste an invite link from the host Mac below.")
                .font(.caption).foregroundStyle(.secondary)
        } else {
            ForEach(hosts, id: \.publicURL) { host in
                Button {
                    chosen = host
                    clientPairingError = nil
                } label: {
                    Label(host.name, systemImage: chosen == host ? "checkmark.circle.fill" : "desktopcomputer")
                }
                .buttonStyle(.plain)
            }
        }
    }

    /// A picked host certified by a public authority is paired with from its code alone; any other needs its invite
    /// (the invite carries the key to pin, which Bonjour never does).
    private var chosenNeedsCodeOnly: Bool {
        chosen.map { !HostChoices.needsInvite($0) } ?? false
    }

    /// What Connect pairs with: the picked host and its typed code, or the pasted invite (which must be for the host
    /// that was picked, if one was).
    private func fieldsToPair() throws -> RemoteClientPairingFields {
        if let chosen, chosenNeedsCodeOnly, let url = chosen.publicURL {
            return RemoteClientPairingFields(remoteURL: url, pairCode: pairCode, spkiPin: nil, libraryPath: "")
        }
        let fields = try RemoteClientPairing.pairingFields(fromInviteOrPayload: clientInvite)
        if let chosen, !HostChoices.invite(fields.remoteURL, isFor: chosen) {
            throw APIError.badRequest("That invite is for another Mac than \(chosen.name). Paste the one shown on \(chosen.name).")
        }
        return fields
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
            let pairingFields = try fieldsToPair()
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
