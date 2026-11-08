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
    // This Mac's own `.ts.net` address, from its own engine; a host in another tailnet always asks for its invite.
    @State private var ownTailnetURL: String?
    /// A failed connect, as the one alert (`sharing.alerts.one-alert-per-failure`); never a line of raw text under the fields.
    @State private var failurePrompt: FailureAlertPrompt?
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
        Section {
            nearbyList

            if chosenNeedsCodeOnly {
                TextField(ConnectSheetModel.codePlaceholder, text: $pairCode)
                    .textFieldStyle(.roundedBorder)
                    .autocorrectionDisabled()
            }

            Text("Or paste a link").font(.caption).foregroundStyle(.secondary)
            TextField(ConnectSheetModel.pastePlaceholder, text: $clientInvite, axis: .vertical)
                .textFieldStyle(.roundedBorder)
                .autocorrectionDisabled()

            // Where the code or link goes, said once.
            if let connectsTo = ConnectSheetModel.connectsTo(
                pickedAddress: chosenNeedsCodeOnly ? chosen?.publicURL : nil, pastedHost: inviteHost) {
                Text(connectsTo).font(.caption).foregroundStyle(.secondary)
            }

            // Asked only after the host answers that it needs a person.
            if ConnectSheetModel.asksForPerson(hostAskedForPerson: needsPerson || linkSignsIn) {
                TextField("Username", text: $personName)
                    .textFieldStyle(.roundedBorder)
                    .autocorrectionDisabled()
                SecureField("Password", text: $personPassword)
                    .textFieldStyle(.roundedBorder)
            }

            HStack {
                Spacer()
                Button(ConnectSheetModel.connectTitle(isConnecting: isClientPairing)) {
                    Task { await connectThisMacAsRemoteClient() }
                }
                .buttonStyle(.borderedProminent)
                .keyboardShortcut(.defaultAction)
                .disabled(!ConnectSheetModel.canConnect(
                    codeRoute: chosenNeedsCodeOnly, code: pairCode, link: clientInvite, isConnecting: isClientPairing,
                    needsPerson: needsPerson || linkSignsIn, name: personName, password: personPassword))
            }
        }
        // A tapped fichero:// link lands here (#3788): prefill it so the person SEES what they are about to connect to
        // and presses Connect themselves. Never pair silently: it repoints this Mac at a remote host. Consumed once.
        .onChange(of: appState.pendingPairingInvite) { _, invite in
            guard let invite, !invite.isEmpty else { return }
            clientInvite = invite
            appState.pendingPairingInvite = nil
        }
        .task {
            nearby.start()
            if EngineConfig.engineIsLocal {
                ownTailnetURL = try? await PairingService(apiRoot: EngineConfig.host).detectedTailnetURL()
            }
            // The link may have arrived BEFORE this view existed (the app was launched by the link, or the sheet opened
            // for it): onChange would never fire for that.
            if let invite = appState.pendingPairingInvite, !invite.isEmpty {
                clientInvite = invite
                appState.pendingPairingInvite = nil
            }
        }
        .onDisappear { nearby.stop() }
        .failureAlert($failurePrompt)
    }

    /// The Fichero Macs nearby, this Mac left out; picking one starts pairing with it (#5892). "Searching…" in grey
    /// while nothing is found yet; an empty list says nothing.
    @ViewBuilder private var nearbyList: some View {
        let hosts = HostChoices.offered(
            nearby.found, ownName: HostChoices.ownServiceName(hostName: ProcessInfo.processInfo.hostName),
            ownTailnetURL: ownTailnetURL)
        if let status = ConnectSheetModel.nearbyStatus(searching: nearby.searching, found: hosts.count) {
            Text(status).font(.caption).foregroundStyle(.secondary)
        }
        ForEach(hosts, id: \.publicURL) { host in
            Button {
                chosen = host
            } label: {
                Label(host.name, systemImage: chosen == host ? "checkmark.circle.fill" : "desktopcomputer")
            }
            .buttonStyle(.plain)
        }
    }

    /// A picked host certified by a public authority is paired with from its code alone; any other needs its invite
    /// (the invite carries the key to pin, which Bonjour never does).
    private var chosenNeedsCodeOnly: Bool {
        chosen.map { !HostChoices.needsInvite($0, ownTailnetURL: ownTailnetURL) } ?? false
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

    /// A pasted link with no code is for a person (Step 8.9): the name and password fields show at once.
    private var linkSignsIn: Bool {
        (try? RemoteClientPairing.pairingFields(fromInviteOrPayload: clientInvite))?.pairCode.isEmpty == true
    }

    /// The host the pasted invite points at, shown read-only so the person sees where they are about to connect.
    private var inviteHost: String? {
        (try? RemoteClientPairing.pairingFields(fromInviteOrPayload: clientInvite))
            .flatMap { URL(string: $0.remoteURL)?.host }
    }

    private func connectThisMacAsRemoteClient() async {
        isClientPairing = true
        defer { isClientPairing = false }

        let previousHost = engineHost
        do {
            let pairingFields = try fieldsToPair()
            // The same sequence the phone runs (`sharing.both-clients-run-the-same-checks`): try the link's addresses, check the
            // contract before any code is sent, pair, keep the token (or revoke), confirm the project, persist.
            let apiRoot = try await RemoteClientPairing.pairAndPersistHost(
                remoteURL: pairingFields.remoteURL,
                pairCode: pairingFields.pairCode,
                deviceName: RemoteClientPairing.defaultDeviceName(),
                expectedSPKIPin: pairingFields.spkiPin,
                libraryPath: pairingFields.libraryPath,
                person: PairingPerson(username: personName, password: personPassword),
                altURLs: pairingFields.altURLs
            )
            // The one procedure that changes the engine host (stop, write, repoint, start, check, roll back) is shared
            // with Settings › Engine › Advanced › Apply (#5916).
            try await engineHostSwitch().run(
                from: previousHost, to: apiRoot.absoluteString,
                notResponding: "Paired successfully, but the verified remote host is not responding now.",
                onFailure: { _ in
                    RemoteClientPairing.rollbackFailedHostSwitch(previousHost: previousHost, attemptedHost: apiRoot)
                })
        } catch {
            if error as? RemoteClientPairingError == .personRequired { needsPerson = true }
            failurePrompt = SharingFailurePrompt.make(
                pairing: error, host: inviteHost ?? chosen?.name ?? "the other Mac",
                offers: [.pasteLinkAgain, .openTailscale, .tryAgain, .openNetworkSettings, .signIn, .checkForUpdates],
                perform: perform, copy: { PlatformPasteboard.writeString($0) })
        }
    }

    /// A fix button of the alert, done here.
    private func perform(_ fix: SharingFailurePrompt.Fix) {
        switch fix {
        case .pasteLinkAgain:
            if let pasted = NSPasteboard.general.string(forType: .string) { clientInvite = pasted }
        case .openTailscale:
            NSWorkspace.shared.open(URL(fileURLWithPath: "/Applications/Tailscale.app"))
        case .tryAgain:
            Task { await connectThisMacAsRemoteClient() }
        case .openNetworkSettings, .openAppSettings:
            if let url = URL(string: "x-apple.systempreferences:com.apple.Network-Settings.extension") { NSWorkspace.shared.open(url) }
        case .signIn:
            needsPerson = true
        case .checkForUpdates:
            SparkleUpdater.shared.checkForUpdates()
        case .turnSharingOffAndOn, .signInAsOwner:
            break
        }
    }

    private func engineHostSwitch() -> EngineHostSwitch {
        .standard(appState: appState, backendService: backendService, libraryManager: libraryManager,
                  setHost: { engineHost = $0 })
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
