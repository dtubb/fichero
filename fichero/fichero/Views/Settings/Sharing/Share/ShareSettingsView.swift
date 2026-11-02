#if canImport(AppKit)
import CoreImage
import CoreImage.CIFilterBuiltins
import FicheroAPIClient
import SwiftUI

// The ONE host-side sharing and pairing surface (#3777).
//
// Turning sharing on is a SINGLE ACTION that does all of its own setup: it derives
// this Mac's address, advertises it on the local network, restarts the engine with
// TLS, mints the certificate pin and the invite. The user never types a URL, never
// sees an SPKI pin, never presses "Apply and Restart Engine". The old second copy
// of this pane (Engine → Backend → "Share This Mac") is gone; its only genuinely
// useful escape hatches — a manual address override and "Reset Invite" — live in
// the single Advanced disclosure at the bottom of this pane.
//
// What the toggle is and isn't: it is a CONVENIENCE ("don't listen"), never a
// safety story. The secret protects the user, not the switch — the engine denies
// any bearer token with no matching device row whatever this flag says. So sharing
// being on is not a risk to explain away; it is a door with a lock on it.

struct ShareSettingsView: View {
    @Environment(AppState.self) var appState
    @Environment(EmbeddedBackendService.self) var backendService
    @Environment(LibraryManager.self) var libraryManager
    @AppStorage(EngineConfig.userDefaultsKey) var engineHost = EngineConfig.defaultHostString
    // Multi-user status is read from the backend (IdentityStore) via
    // `backendMultiuser`, not a local flag, so this tab agrees with Users +
    // Engine (#3331).
    @AppStorage(EngineConfig.multiuserEnabledKey) var multiuserEnabled = false
    @AppStorage(RemoteAccessConfig.hostingEnabledKey) var hostingEnabled = false
    @AppStorage(RemoteAccessConfig.bonjourEnabledKey) var bonjourEnabled = false
    @AppStorage(RemoteAccessConfig.publicBaseURLKey) var publicBaseURL = ""

    @State var pairingCode: PairingCodeRecord?
    @State var pairedDevices: [PairedDeviceRecord] = []
    @State var spkiPin = ""
    @State var shareError: String?
    @State var isApplyingChange = false
    @State var isGeneratingCode = false
    @State var isLoadingDevices = false
    @State var didBootstrap = false
    @State var copiedInvite = false
    @State var copyNote: String?
    @State var addressDraft = ""
    @State var sharingState: SharingStateRecord?
    @State var detectedTailnetURL: String?
    @State var firewallVerdict = FirewallCheck.Verdict.unknown
    @State var hostAddresses: [HostAddressRecord] = []
    @State var selectedDevices = Set<String>()
    @State var confirmRemoveSelected = false
    /// The one sheet this pane presents: two `.sheet(isPresented:)` on the same view race, and only one shows reliably.
    enum ActiveSheet: Identifiable {
        case addDevice, connect
        var id: Self { self }
    }
    @State var activeSheet: ActiveSheet?
    /// The QR, drawn once per link and kept (`sharing.qr-drawn-once-per-payload`): a computed image was rebuilt on every
    /// body evaluation (the Devices poll every 10 s), which the person saw as the picture flashing.
    @State var qrImage: PlatformImage?
    /// The engine process (health's pid) that minted the code on the card: a code outlives a health check, never a restart.
    @State var codeEnginePID: Int?
    /// The engine process health last named (`refreshEnginePID`); what `codeEnginePID` is compared with.
    @State var healthEnginePID: Int?
    /// Which address the QR and Copy Link carry (`sharing.share-sheet-offers-both-addresses`); nil = the model's default.
    @State var addressChoice: AddressChoice?
    var showAddDevice: Bool {
        get { activeSheet == .addDevice }
        nonmutating set { activeSheet = newValue ? .addDevice : (activeSheet == .addDevice ? nil : activeSheet) }
    }
    var showConnect: Bool {
        get { activeSheet == .connect }
        nonmutating set { activeSheet = newValue ? .connect : (activeSheet == .connect ? nil : activeSheet) }
    }

    let qrContext = CIContext()

    // Forwards to the single definition in `RemoteAccessConfig` so this pane and
    // the Share sheet cannot derive different addresses (#5042).
    static var autoLocalBaseURL: String { RemoteAccessConfig.autoLocalBaseURL }

    var body: some View {
        Form {
            Section {
                Toggle(SharingPaneText.switchTitle, isOn: sharingBinding)
                    .disabled(isApplyingChange || !EngineConfig.engineIsLocal)
                if let line = SharingPaneText.statusLine(
                    isOn: hostingEnabled, isApplying: isApplyingChange, error: shareError,
                    engineIsLocal: EngineConfig.engineIsLocal) {
                    Text(line)
                        .font(.caption)
                        .foregroundStyle(shareError == nil ? Color.secondary : Color.red)
                }
            }

            if SharingPaneText.showsDevices(isOn: hostingEnabled, engineIsLocal: EngineConfig.engineIsLocal) {
                devicesSection
            }

            if multiuserEnabled {
                PendingInvitesSection()
            }

            if SharingPaneText.showsConnect(isOn: hostingEnabled, engineIsLocal: EngineConfig.engineIsLocal) {
                Section {
                    Button(SharingPaneText.connect) { showConnect = true }
                }
            }

            advancedSection
        }
        .formStyle(.grouped)
        .sheet(item: $activeSheet) { sheet in
            switch sheet {
            case .addDevice: addDeviceSheet
            case .connect: connectSheet
            }
        }
        // A tapped invite link opens the Connect sheet with the link filled in (`sharing.settings.connect-sheet`).
        .onChange(of: appState.pendingPairingInvite) { _, invite in
            if ConnectSheetModel.opensFor(pendingInvite: invite) { showConnect = true }
        }
        .task {
            if ConnectSheetModel.opensFor(pendingInvite: appState.pendingPairingInvite) { showConnect = true }
            loadSPKIPin()
            addressDraft = publicBaseURL
            // Refresh the backend's real multi-user state so this pane matches Accounts (#3331).
            await appState.identityStore.load()
            multiuserEnabled = appState.identityStore.multiuserEnabled
            if let note = MultiuserMigration.takeNote(defaults: EngineConfig.defaults) { shareError = note }
            if hostingEnabled && publicBaseURL.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                publicBaseURL = Self.autoLocalBaseURL
                await applySharing()
            } else if hostingEnabled, appState.isBackendRunning {
                await refreshDevices()
            }
            await refreshSharingState()
            didBootstrap = true
        }
        // The Devices list refreshes itself while sharing is on: there is no Refresh button.
        .task(id: hostingEnabled) {
            guard hostingEnabled else { return }
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(10))
                if Task.isCancelled { return }
                if didBootstrap, appState.isBackendRunning {
                    await refreshDevices()
                    // The forward is made just after the engine is ready: while it reads `none`, ask again (review N1).
                    if PairingCardRefresh.readsForwardAgain(stateLoaded: sharingState != nil, forward: sharingState?.tailnetForward) {
                        await refreshSharingState()
                    }
                }
            }
        }
        .task(id: refreshKey) {
            guard didBootstrap else { return }
            await refreshPairingCode()
        }
        // The engine coming back mints when the card has nothing to show, or shows a code another engine process minted
        // (a restart loses the engine's codes); its going away never clears the card.
        .onChange(of: appState.isBackendRunning) { _, running in
            guard didBootstrap else { return }
            Task {
                if running { await refreshEnginePID() }  // the pid health names now, to compare with the code's
                guard PairingCardRefresh.mintsWhenEngineChanges(isRunning: running, hasCode: pairingCode != nil,
                                                                blocked: pairingBlocker != nil, sameEngine: codeIsFromThisEngine)
                else { return }
                await refreshPairingCode()
            }
        }
        .task(id: inviteLinkString) { qrImage = makeQRCodeImage() }
        // A code is replaced when it expires, not left on screen past the time it names (#5915). The task is keyed on
        // the code, so a new code (or none) cancels the wait; a failed mint leaves no code and so no retry loop.
        .task(id: pairingCode?.code) {
            guard didBootstrap, let expiresAt = pairingCode?.expiresAt else { return }
            // the code changed or the card went away
            do { try await Task.sleep(for: PairingCodeRenewal.wait(until: expiresAt)) } catch { return }
            // Sharing was turned off while the code was up: an expired code must not linger on the card.
            guard pairingBlocker == nil else { pairingCode = nil; return }
            // The old code stays on screen until the new one lands: clearing it first would change this task's key
            // and cancel the renewal itself (review 597).
            switch await PairingCodeRenewal.renew(mint: { try await PairingService(apiRoot: EngineConfig.host).createPairingCode() }) {
            case .fresh(let code): pairingCode = code
            case .failed(let message): pairingCode = nil; shareError = message
            case .cancelled: break
            }
        }
        .onChange(of: publicBaseURL) { _, newValue in
            loadSPKIPin()
            addressDraft = newValue
        }
    }
}
#endif
