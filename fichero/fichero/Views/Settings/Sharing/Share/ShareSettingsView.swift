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
    @State var selectedDevices = Set<String>()
    @State var confirmRemoveSelected = false
    @State var showAddDevice = false
    @State var showConnect = false

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

            Section {
                Button(SharingPaneText.connect) { showConnect = true }
            }

            advancedSection
        }
        .formStyle(.grouped)
        .sheet(isPresented: $showAddDevice) { addDeviceSheet }
        .sheet(isPresented: $showConnect) { connectSheet }
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
                if didBootstrap, appState.isBackendRunning { await refreshDevices() }
            }
        }
        .task(id: refreshKey) {
            guard didBootstrap else { return }
            await refreshPairingCode()
        }
        // A code is replaced when it expires, not left on screen past the time it names (#5915). The task is keyed on
        // the code, so a new code (or none) cancels the wait; a failed mint leaves no code and so no retry loop.
        .task(id: pairingCode?.code) {
            guard didBootstrap, let expiresAt = pairingCode?.expiresAt else { return }
            do { try await Task.sleep(for: PairingCodeRenewal.wait(until: expiresAt)) } catch { return }  // the code changed or the card went away
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

    /// The Devices list: name and when last seen, `+ Add Device…` and `−` (multi-select Remove). Blank when empty, no Refresh.
    @ViewBuilder
    private var devicesSection: some View {
        let devices = activePairedDevices(from: pairedDevices)
        Section("Devices") {
            List(devices, selection: $selectedDevices) { device in
                HStack {
                    Text(device.name)
                    Spacer()
                    Text(device.lastSeen, style: .relative)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                .tag(device.id)
            }
            .frame(minHeight: devices.isEmpty ? 0 : 80)
            HStack {
                Button(SharingPaneText.addDevice) { showAddDevice = true }
                Button("−") { confirmRemoveSelected = true }
                    .help("Remove the selected devices")
                    .disabled(!SharingPaneText.canRemove(selected: selectedDevices.count, engineIsLocal: EngineConfig.engineIsLocal))
            }
        }
        .confirmationDialog(
            SharingPaneText.removeQuestion(
                count: selectedDevices.count, firstName: devices.first { selectedDevices.contains($0.id) }?.name),
            isPresented: $confirmRemoveSelected,
            titleVisibility: .visible
        ) {
            Button("Remove", role: .destructive) { Task { await revokeSelected() } }
            Button("Cancel", role: .cancel) {}
        } message: {
            let also = selectedDevices.flatMap { devicesRevokedWith($0, in: pairedDevices) }
                .filter { !selectedDevices.contains($0.id) }
            Text(also.isEmpty ? "They will no longer be able to connect."
                 : "They will no longer be able to connect. They paired \(Set(also.map(\.name)).sorted().formatted()), which will be removed too.")
        }
    }

    /// Add Device: asks for nothing: the QR, the code, when it expires, Copy Link and Done (`sharing.settings.add-device-sheet`).
    @ViewBuilder
    private var addDeviceSheet: some View {
        let phase = AddDeviceSheetModel.phase(
            blocker: pairingBlocker, hasCode: pairingCode != nil, hasLink: inviteLinkString != nil,
            isWorking: isApplyingChange || isGeneratingCode)
        VStack(spacing: 12) {
            switch phase {
            case .finishing:
                ProgressView("Finishing setup…")
            case .ready, .notReady:
                if let image = qrCodeImage {
                    Image(platformImage: image)
                        .interpolation(.none)
                        .resizable()
                        .frame(width: 220, height: 220)
                        .accessibilityLabel("Pairing QR code")
                }
                if let code = pairingCode {
                    Text(AddDeviceSheetModel.codeText(code.code))
                        .font(.title2.monospacedDigit())
                    Text(AddDeviceSheetModel.expiresText(expiresAt: code.expiresAt))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                if phase == .notReady {
                    Text("Not ready yet").font(.caption).foregroundStyle(.secondary)
                }
            case .finishSetup:
                Button("Finish Setup") { if let blocker = pairingBlocker { Task { await resolve(blocker) } } }
                    .buttonStyle(.borderedProminent)
            case .start:
                Button("Start") { if let blocker = pairingBlocker { Task { await resolve(blocker) } } }
                    .buttonStyle(.borderedProminent)
            case .failed(let line):
                Text(line).foregroundStyle(.secondary)
            }
            if let note = copyNote {
                Text(note).font(.caption).foregroundStyle(.red)
            }
            HStack {
                Button(copiedInvite ? "Link Copied" : "Copy Link", action: copyInvite)
                    .disabled(phase != .ready)
                Spacer()
                Button("Done") { showAddDevice = false; Task { await refreshDevices() } }
                    .keyboardShortcut(.defaultAction)
            }
        }
        .padding()
        .frame(minWidth: 320)
        .onChange(of: inviteLinkString) { _, _ in copyNote = nil }
    }

    /// Connect to Another Mac: hosts the existing client pairing section on a sheet (`sharing.settings.connect-sheet`).
    private var connectSheet: some View {
        VStack(spacing: 12) {
            Form {
                MacRemoteClientPairingSection(
                    appState: appState, backendService: backendService, libraryManager: libraryManager)
            }
            .formStyle(.grouped)
            HStack {
                Spacer()
                Button("Cancel") { showConnect = false }.keyboardShortcut(.cancelAction)
            }
        }
        .padding()
        .frame(minWidth: 460, minHeight: 360)
    }
}
#endif
