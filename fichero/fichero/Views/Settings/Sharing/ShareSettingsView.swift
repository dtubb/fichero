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

// swiftlint:disable file_length
// swiftlint:disable:next type_body_length
struct ShareSettingsView: View {
    @Environment(AppState.self) var appState
    @Environment(EmbeddedBackendService.self) var backendService
    @Environment(LibraryManager.self) var libraryManager
    @AppStorage(EngineConfig.userDefaultsKey) private var engineHost = EngineConfig.defaultHostString
    // Multi-user status is read from the backend (IdentityStore) via
    // `backendMultiuser`, not a local flag, so this tab agrees with Users +
    // Engine (#3331).
    @AppStorage(RemoteAccessConfig.hostingEnabledKey) private var hostingEnabled = false
    @AppStorage(RemoteAccessConfig.bonjourEnabledKey) private var bonjourEnabled = false
    @AppStorage(RemoteAccessConfig.publicBaseURLKey) private var publicBaseURL = ""

    @State private var pairingCode: PairingCodeRecord?
    @State private var pairedDevices: [PairedDeviceRecord] = []
    @State private var authzSnapshot: Components.Schemas.LibraryAuthzSnapshot?
    @State private var authzError: String?
    @State private var isLoadingAuthz = false
    @State private var spkiPin = ""
    @State private var shareError: String?
    @State private var isApplyingChange = false
    @State private var isGeneratingCode = false
    @State private var isLoadingDevices = false
    @State private var didBootstrap = false
    @State private var copiedInvite = false
    @State private var addressDraft = ""
    @State private var confirmRemoveAllDevices = false

    private let qrContext = CIContext()

    // Derives https://<hostname>.local:<port> from the system Bonjour name.
    // Port mirrors EngineConfig.defaultHostString so both stay in sync.
    private static var autoLocalBaseURL: String {
        var host = ProcessInfo.processInfo.hostName.lowercased()
        if !host.hasSuffix(".local") {
            host = (host.components(separatedBy: ".").first ?? host) + ".local"
        }
        let port = URL(string: EngineConfig.defaultHostString)?.port ?? 8765
        return "https://\(host):\(port)"
    }

    var body: some View {
        Form {
            securitySection

            Section {
                Toggle(isOn: sharingBinding) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(hostingEnabled ? "On" : "Off")
                            .font(.headline)
                        Text("Share Fichero on this Mac with other devices.")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
                .disabled(isApplyingChange || !EngineConfig.engineIsLocal)
                .padding(.vertical, 4)

                if hostingEnabled || pairingBlocker == .engineIsRemote {
                    PairingCardView(
                        pairingCode: pairingCode,
                        qrCodeImage: qrCodeImage,
                        publicURL: validatedPublicURL?.absoluteString,
                        inviteLink: inviteLinkString,
                        isGeneratingPairingCode: isGeneratingCode,
                        blocker: pairingBlocker,
                        errorMessage: shareError,
                        isResolving: isApplyingChange,
                        onResolve: { blocker in Task { await resolve(blocker) } },
                        copiedInvite: copiedInvite,
                        onCopyInvite: copyInvite
                    )
                }
            }

            if hostingEnabled {
                Section {
                    PairedDevicesSectionView(
                        devices: activePairedDevices(from: pairedDevices),
                        isLoading: isLoadingDevices,
                        canHostRemoteAccess: EngineConfig.engineIsLocal,
                        onRefresh: { Task { await refreshDevices() } },
                        onRevoke: { deviceID in Task { await revoke(deviceID: deviceID) } }
                    )
                }
            }

            advancedSection

            #if canImport(AppKit)
            // Client side of pairing — connect THIS Mac to another Fichero library
            // (consolidated here so all connection/pairing lives in Library Access).
            MacRemoteClientPairingSection(
                appState: appState,
                backendService: backendService,
                libraryManager: libraryManager
            )
            #endif
        }
        .formStyle(.grouped)
        .task {
            loadSPKIPin()
            addressDraft = publicBaseURL
            // Refresh the backend's real multi-user state so this tab's status
            // matches Users + Engine (#3331).
            await appState.identityStore.load()
            if hostingEnabled && publicBaseURL.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                publicBaseURL = Self.autoLocalBaseURL
                await applySharing()
            } else if hostingEnabled, appState.isBackendRunning {
                await refreshDevices()
            }
            await loadAuthzSnapshot()
            didBootstrap = true
        }
        .task(id: securityRefreshKey) {
            guard didBootstrap else { return }
            await loadAuthzSnapshot()
        }
        .task(id: refreshKey) {
            guard didBootstrap else { return }
            await refreshPairingCode()
        }
        .onChange(of: publicBaseURL) { _, newValue in
            loadSPKIPin()
            addressDraft = newValue
        }
    }

    // MARK: - Blocker

    /// Why the pairing card cannot show a QR right now — each precondition named
    /// honestly, in the order it must hold (#3776/#3769).
    private var pairingBlocker: PairingBlocker? {
        guard EngineConfig.engineIsLocal else { return .engineIsRemote }
        guard appState.isBackendRunning else { return .engineNotRunning }
        guard hostingEnabled else { return .sharingNotStarted }

        do {
            _ = try validatedHostedRemoteURL(from: publicBaseURL)
        } catch let error as RemoteURLValidationError {
            switch error {
            case .blank: return .addressMissing
            case .insecureRemoteTransport: return .addressInsecure
            default: return .addressInvalid(error.localizedDescription)
            }
        } catch {
            return .addressInvalid(error.localizedDescription)
        }

        // The pin is derived, not typed — and the derivation is optional. If it comes
        // back nil the card used to go blank, which is the very disease #3769 is
        // about. The app CAN fix this itself: restarting the engine mints the TLS
        // material and re-derives the pin.
        guard hasValidSPKIPin else { return .pinNotDerived }
        return nil
    }

    /// Perform the blocker's own cure. Only offered where the app can genuinely do
    /// the setup itself — the whole point of the design is that it does, rather than
    /// telling the user to go and do it.
    private func resolve(_ blocker: PairingBlocker) async {
        switch blocker {
        case .engineNotRunning:
            isApplyingChange = true
            shareError = nil
            defer { isApplyingChange = false }
            do {
                try await backendService.start()
            } catch {
                shareError = error.localizedDescription
            }
            loadSPKIPin()
        case .sharingNotStarted:
            hostingEnabled = true
            bonjourEnabled = true
            if publicBaseURL.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                publicBaseURL = Self.autoLocalBaseURL
            }
            await applySharing()
        case .engineIsRemote, .addressMissing, .addressInsecure, .addressInvalid, .pinNotDerived:
            break  // no button offered — see PairingBlocker.actionTitle
        }
    }

    // MARK: - Security summary

    @ViewBuilder
    private var securitySection: some View {
        Section("Security") {
            // The authoritative multi-user toggle lives in Engine settings
            // (owns fichero.multiuser.enabled, restart-applied). Show it here
            // read-only so the sharing surface reflects the current mode.
            LabeledContent("Multi-user mode") {
                Text(backendMultiuser ? "Enabled" : "Disabled")
                    .foregroundStyle(backendMultiuser ? .primary : .secondary)
            }

            LabeledContent("Backend authz") {
                Text(backendAuthzStatus)
                    .foregroundStyle(backendAuthzStatus == "Enabled" ? .primary : .secondary)
            }

            if isLoadingAuthz {
                LabeledContent("Library ACL") {
                    ProgressView().controlSize(.small)
                }
            } else if let authzSnapshot {
                LabeledContent("Library ACL") {
                    Text(authzSnapshot.currentUserRole?.capitalized ?? "No role")
                        .foregroundStyle(.secondary)
                }
                LabeledContent("Access") {
                    Text(authzAccessSummary(authzSnapshot))
                        .foregroundStyle(.secondary)
                }
            } else if let authzError {
                LabeledContent("Library ACL") {
                    Text(authzError)
                        .foregroundStyle(.red)
                }
            } else {
                LabeledContent("Library ACL") {
                    Text("Not loaded")
                        .foregroundStyle(.secondary)
                }
            }

            LabeledContent("Pairing") {
                Text(hostingEnabled ? "\(activePairedDevices(from: pairedDevices).count) devices" : "Off")
                    .foregroundStyle(.secondary)
            }
        }
    }

    // MARK: - Advanced (the ONE escape hatch)

    @ViewBuilder
    private var advancedSection: some View {
        Section {
            DisclosureGroup("Advanced") {
                // Use an override only for an address the app cannot infer, such as Tailscale or a fixed IP.
                LabeledContent("Automatic address") {
                    Text(Self.autoLocalBaseURL)
                        .font(.caption.monospaced())
                        .textSelection(.enabled)
                        .foregroundStyle(.secondary)
                }

                TextField("Address other devices use", text: $addressDraft)
                    .textFieldStyle(.roundedBorder)
                    .autocorrectionDisabled()

                Text("A literal IP address, a .local hostname, or a Tailscale .ts.net hostname. "
                     + "It must be https:// so the connection can be pinned.")
                    .font(.caption)
                    .foregroundStyle(.secondary)

                HStack {
                    Button("Use This Address") {
                        publicBaseURL = addressDraft.trimmingCharacters(in: .whitespacesAndNewlines)
                        Task { await applySharing() }
                    }
                    .disabled(isApplyingChange || addressDraft == publicBaseURL)

                    Button("Restore Automatic") {
                        publicBaseURL = Self.autoLocalBaseURL
                        Task { await applySharing() }
                    }
                    .disabled(isApplyingChange || publicBaseURL == Self.autoLocalBaseURL)
                }

                Divider()

                // The only invite-rotation affordance in the app: mints a fresh
                // one-time code and invalidates the one already on screen.
                Button(isGeneratingCode ? "Resetting Invite…" : "Reset Invite") {
                    Task { await refreshPairingCode() }
                }
                .disabled(isApplyingChange || isGeneratingCode || pairingBlocker != nil)

                Button("Remove All Devices", role: .destructive) {
                    confirmRemoveAllDevices = true
                }
                .disabled(!EngineConfig.engineIsLocal || activePairedDevices(from: pairedDevices).isEmpty)
            }
        }
        .confirmationDialog(
            "Remove all connected devices?",
            isPresented: $confirmRemoveAllDevices,
            titleVisibility: .visible
        ) {
            Button("Remove All Devices", role: .destructive) {
                Task { await revokeAllDevices() }
            }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("Every device that has joined this library will have to scan a new QR code to get back in.")
        }
    }

    /// The engine's real multi-user state — the single source of truth (#3331),
    /// shared with the Users + Engine tabs so all three agree. Reads
    /// `GET /api/auth/identity` via IdentityStore, never the local desired flag.
    private var backendMultiuser: Bool { appState.identityStore.multiuserEnabled }

    private var backendAuthzStatus: String {
        if !appState.isBackendRunning {
            return "Unavailable"
        }
        return backendMultiuser ? "Enabled" : "Disabled"
    }

    private var securityRefreshKey: String {
        [
            appState.isBackendRunning.description,
            backendMultiuser.description,
            hostingEnabled.description,
            libraryManager.globalLibrary?.id.uuidString ?? "none"
        ].joined(separator: "|")
    }

    // MARK: - Pairing payload

    private var hasValidSPKIPin: Bool {
        (try? RemoteCertificatePinning.validatedSPKIPin(spkiPin)) != nil
    }

    private var validatedPublicURL: URL? {
        try? validatedHostedRemoteURL(from: publicBaseURL)
    }

    private var advertisedPairingService: PairingService? {
        guard let publicURL = validatedPublicURL else { return nil }
        return PairingService(apiRoot: publicURL)
    }

    private var pairingQRPayload: PairingQRCodePayload? {
        guard let pairingCode, let advertisedPairingService else { return nil }
        guard let normalizedPin = try? RemoteCertificatePinning.validatedSPKIPin(spkiPin) else { return nil }
        return advertisedPairingService.buildQRCodePayload(
            from: pairingCode,
            spki: normalizedPin,
            libraryPath: sharedLibraryPath
        )
    }

    private var inviteLinkString: String? {
        guard let pairingQRPayload else { return nil }
        return try? RemoteClientPairing.inviteLinkString(from: pairingQRPayload)
    }

    private var qrCodeImage: PlatformImage? {
        guard let pairingQRPayload else { return nil }
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        guard let data = try? encoder.encode(pairingQRPayload) else { return nil }
        let filter = CIFilter.qrCodeGenerator()
        filter.message = data
        filter.correctionLevel = "M"
        guard let output = filter.outputImage?.transformed(by: CGAffineTransform(scaleX: 12, y: 12)),
              let cgImage = qrContext.createCGImage(output, from: output.extent) else { return nil }
        return PlatformImage(cgImage: cgImage, size: .zero)
    }

    private func copyInvite() {
        guard let inviteLinkString else { return }
        PlatformPasteboard.writeString(inviteLinkString)
        copiedInvite = true
        Task {
            try? await Task.sleep(for: .seconds(2))
            copiedInvite = false
        }
    }

    // MARK: - Authz

    @MainActor
    private func loadAuthzSnapshot() async {
        guard let library = libraryManager.globalLibrary else {
            authzSnapshot = nil
            authzError = nil
            return
        }

        isLoadingAuthz = true
        authzError = nil
        defer { isLoadingAuthz = false }

        do {
            authzSnapshot = try await library.actionsService.loadLibraryAuthzSnapshot()
        } catch {
            authzSnapshot = nil
            authzError = error.localizedDescription
        }
    }

    private func authzAccessSummary(_ snapshot: Components.Schemas.LibraryAuthzSnapshot) -> String {
        if snapshot.canManageRoles { return "Owner" }
        if snapshot.targetCanWrite { return "Read / Write" }
        if snapshot.targetCanRead { return "Read only" }
        return "Blocked"
    }

    // MARK: - State management

    private var refreshKey: String {
        [hostingEnabled.description, publicBaseURL, spkiPin, engineHost,
         appState.isBackendRunning.description, didBootstrap.description]
            .joined(separator: "|")
    }

    /// ONE ACTION. Flipping this on derives the address, advertises the Mac, restarts
    /// the engine with TLS and mints the invite — the user does not do our setup.
    private var sharingBinding: Binding<Bool> {
        Binding(
            get: { hostingEnabled },
            set: { newValue in
                hostingEnabled = newValue
                if newValue {
                    bonjourEnabled = true
                    if publicBaseURL.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                        publicBaseURL = Self.autoLocalBaseURL
                    }
                }
                Task { await applySharing() }
            }
        )
    }

    private func applySharing() async {
        isApplyingChange = true
        shareError = nil
        defer { isApplyingChange = false }
        if !hostingEnabled {
            RemoteCertificatePinning.clearAdvertisedSPKIPin(hostString: publicBaseURL)
            RemoteCertificatePinning.clearPersistedSPKIPin(hostString: publicBaseURL)
            loadSPKIPin()
        }

        if backendService.isUsingExternalBackend {
            await appState.checkBackendHealth()
            appState.reconfigureGeneratedClientsForCurrentHost()
            libraryManager.reconfigureGeneratedClientsForCurrentHost()
            // The external engine already serves TLS; the health handshake bootstraps
            // its pin. Load it as part of THIS action so the QR appears without a
            // separate "Prepare Certificate" step (#3811).
            loadSPKIPin()
            if hostingEnabled {
                await refreshDevices()
            }
            return
        }

        backendService.stop()
        do {
            try await backendService.start()
            await appState.checkBackendHealth()
            appState.reconfigureGeneratedClientsForCurrentHost()
            libraryManager.reconfigureGeneratedClientsForCurrentHost()
            // Load the SPKI pin AFTER the health handshake. Turning sharing on mints
            // and persists the certificate as part of THIS action, so by the time the
            // pairing card evaluates its blocker the pin is ready and the QR appears —
            // no separate "Prepare Certificate" step (#3811). Reading it here covers
            // both the pin the restart pre-persists and one the live TLS handshake
            // bootstraps.
            loadSPKIPin()
            if hostingEnabled { await refreshDevices() }
        } catch {
            shareError = error.localizedDescription
        }
    }

    private func refreshPairingCode() async {
        pairingCode = nil
        shareError = nil
        guard pairingBlocker == nil else { return }
        isGeneratingCode = true
        defer { isGeneratingCode = false }
        do {
            try await Task.sleep(for: .milliseconds(200))
            try Task.checkCancellation()
            pairingCode = try await PairingService(apiRoot: EngineConfig.host).createPairingCode()
        } catch {
            if !(error is CancellationError) { shareError = error.localizedDescription }
        }
    }

    private func refreshDevices() async {
        isLoadingDevices = true
        defer { isLoadingDevices = false }
        guard EngineConfig.engineIsLocal else { return }
        do {
            pairedDevices = try await PairingService(apiRoot: EngineConfig.host).listDevices()
        } catch {
            shareError = error.localizedDescription
        }
    }

    private func revoke(deviceID: String) async {
        shareError = nil
        guard EngineConfig.engineIsLocal else { return }
        do {
            try await PairingService(apiRoot: EngineConfig.host).revokeDevice(id: deviceID)
            await refreshDevices()
        } catch {
            shareError = error.localizedDescription
        }
    }

    private func revokeAllDevices() async {
        shareError = nil
        guard EngineConfig.engineIsLocal else { return }
        let service = PairingService(apiRoot: EngineConfig.host)
        do {
            for device in activePairedDevices(from: pairedDevices) {
                try await service.revokeDevice(id: device.id)
            }
        } catch {
            shareError = error.localizedDescription
        }
        await refreshDevices()
    }

    private func loadSPKIPin() {
        spkiPin = RemoteAccessConfig.hostedBackendSPKIPin(hostString: publicBaseURL) ?? ""
    }

    private var sharedLibraryPath: String? {
        if let currentLibraryId = libraryManager.currentLibraryId,
           let library = libraryManager.getLibrary(id: currentLibraryId) {
            return library.url.path
        }
        return libraryManager.globalLibrary?.url.path
    }
}
#endif
// swiftlint:enable file_length
