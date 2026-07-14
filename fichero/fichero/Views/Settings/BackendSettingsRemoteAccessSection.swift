#if canImport(AppKit)
// swiftlint:disable file_length
import CoreImage
import CoreImage.CIFilterBuiltins
import FicheroAPIClient
import SwiftUI

private let hostedRemoteAccessHelpText = """
Use a private reachable URL such as a literal IP address, .local hostname, or Tailscale .ts.net hostname.
Bonjour only announces that this Mac is available; the QR code still carries the URL the client should call.
"""

// swiftlint:disable:next type_body_length
struct BackendSettingsRemoteAccessSection: View {
    @Bindable private var appState: AppState
    @Bindable private var backendService: EmbeddedBackendService
    @Bindable private var libraryManager: LibraryManager
    @AppStorage(EngineConfig.userDefaultsKey) private var engineHost = EngineConfig.defaultHostString
    @AppStorage(RemoteAccessConfig.hostingEnabledKey) private var hostingEnabled = false
    @AppStorage(RemoteAccessConfig.bonjourEnabledKey) private var bonjourEnabled = false
    @AppStorage(RemoteAccessConfig.publicBaseURLKey) private var publicBaseURL = ""

    @State private var pairingCode: PairingCodeRecord?
    @State private var pairedDevices: [PairedDeviceRecord] = []
    @State private var pairingError: String?
    @State private var isRestartingHost = false
    @State private var isGeneratingPairingCode = false
    @State private var isLoadingDevices = false
    @State private var didBootstrapPairingCard = false
    @State private var spkiPin = ""
    @State private var copiedInvite = false

    init(
        appState: AppState,
        backendService: EmbeddedBackendService,
        libraryManager: LibraryManager
    ) {
        self._appState = Bindable(wrappedValue: appState)
        self._backendService = Bindable(wrappedValue: backendService)
        self._libraryManager = Bindable(wrappedValue: libraryManager)
    }

    private let qrContext = CIContext()

    var body: some View {
        Section("Share This Mac") {
            TextField("Sharing address", text: $publicBaseURL)
                .autocorrectionDisabled()
                .disabled(!hostingEnabled)

            PairingCardView(
                pairingCode: pairingCode,
                qrCodeImage: qrCodeImage,
                publicURL: validatedPublicURL?.absoluteString,
                inviteLink: inviteLinkString,
                isGeneratingPairingCode: isGeneratingPairingCode,
                blocker: pairingBlocker,
                errorMessage: pairingError,
                isResolving: isRestartingHost,
                onResolve: { blocker in Task { await resolve(blocker) } },
                copiedInvite: copiedInvite,
                onCopyInvite: copyInvite
            )

            PairedDevicesSectionView(
                devices: activePairedDevices(from: pairedDevices),
                isLoading: isLoadingDevices,
                canHostRemoteAccess: canHostRemoteAccess,
                onRefresh: { Task { await refreshPairedDevices() } },
                onRevoke: { deviceID in Task { await revoke(deviceID: deviceID) } }
            )

            AdvancedRemoteAccessSection(
                hostingEnabled: $hostingEnabled,
                bonjourEnabled: $bonjourEnabled,
                publicBaseURL: $publicBaseURL,
                canHostRemoteAccess: canHostRemoteAccess,
                isRestartingHost: isRestartingHost,
                isRefreshingInvite: isGeneratingPairingCode,
                canResetInvite: pairingBlocker == nil,
                onResetInvite: { Task { await refreshPairingCard() } },
                onApply: { Task { await applyHostingChanges() } }
            )
        }
        .task {
            loadAdvertisedSPKIPin()
            if !canHostRemoteAccess {
                pairedDevices = []
            } else if hostingEnabled, appState.isBackendRunning {
                await refreshPairedDevices()
            }
            didBootstrapPairingCard = true
        }
        .task(id: pairingRefreshKey) {
            guard didBootstrapPairingCard else { return }
            await refreshPairingCard()
        }
        .onChange(of: publicBaseURL) { _, _ in
            loadAdvertisedSPKIPin()
        }
    }

    private var canHostRemoteAccess: Bool {
        EngineConfig.engineIsLocal
    }

    private var ownerPairingService: PairingService? {
        guard canHostRemoteAccess else { return nil }
        return PairingService(apiRoot: EngineConfig.host)
    }

    private var advertisedPairingService: PairingService? {
        guard let publicURL = try? validatedHostedRemoteURL(from: publicBaseURL) else { return nil }
        return PairingService(apiRoot: publicURL)
    }

    private var hasValidSPKIPin: Bool {
        (try? RemoteCertificatePinning.validatedSPKIPin(spkiPin)) != nil
    }

    private var validatedPublicURL: URL? {
        try? validatedHostedRemoteURL(from: publicBaseURL)
    }

    private var pairingRefreshKey: String {
        [
            hostingEnabled.description,
            publicBaseURL,
            spkiPin,
            engineHost,
            appState.isBackendRunning.description,
            didBootstrapPairingCard.description
        ].joined(separator: "|")
    }

    private var inviteLinkString: String? {
        guard let pairingCode, let advertisedPairingService else { return nil }
        guard let normalizedSPKIPin = try? RemoteCertificatePinning.validatedSPKIPin(spkiPin) else {
            return nil
        }
        let payload = advertisedPairingService.buildQRCodePayload(
            from: pairingCode,
            spki: normalizedSPKIPin,
            libraryPath: sharedLibraryPath
        )
        return try? RemoteClientPairing.inviteLinkString(from: payload)
    }

    private var qrCodeImage: PlatformImage? {
        guard let pairingCode, let advertisedPairingService else { return nil }
        guard let normalizedSPKIPin = try? RemoteCertificatePinning.validatedSPKIPin(spkiPin) else {
            return nil
        }

        let payload = advertisedPairingService.buildQRCodePayload(
            from: pairingCode,
            spki: normalizedSPKIPin,
            libraryPath: sharedLibraryPath
        )
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        guard let data = try? encoder.encode(payload) else { return nil }

        let filter = CIFilter.qrCodeGenerator()
        filter.message = data
        filter.correctionLevel = "M"
        guard let output = filter.outputImage?.transformed(by: CGAffineTransform(scaleX: 12, y: 12)),
              let cgImage = qrContext.createCGImage(output, from: output.extent) else {
            return nil
        }
        return PlatformImage(cgImage: cgImage, size: .zero)
    }

    /// Why the pairing card cannot show a QR right now — each precondition named
    /// HONESTLY, with the fix the app can perform itself (#3776/#3769).
    ///
    /// The old chain returned one `String?` and the card printed a fixed headline
    /// ("Secure sharing needs HTTPS") over ALL of them — so a stopped engine was
    /// reported as an HTTPS problem. And three separate causes shared one message
    /// that named no place and offered no button. Both are fixed here: the card
    /// asks the blocker for its own headline, and offers `actionTitle` when the app
    /// can cure it without the user doing setup by hand.
    private var pairingBlocker: PairingBlocker? {
        guard canHostRemoteAccess else { return .engineIsRemote }
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

        // THE TRAP (#3776 review): the pin is derived, not typed — and the
        // derivation is optional. If it comes back nil the card used to go blank,
        // which is the very disease #3769 is about. The app CAN fix this itself:
        // restarting the engine mints the TLS material and re-derives the pin.
        guard hasValidSPKIPin else { return .pinNotDerived }
        return nil
    }

    /// Perform the blocker's own cure. Only offered where the app can genuinely do
    /// the setup itself — the whole point of the design is that it does, rather
    /// than telling the user to go and do it.
    private func resolve(_ blocker: PairingBlocker) async {
        switch blocker {
        case .engineNotRunning:
            // Mark busy so the button disables — without this a double-tap races a
            // second start(). (start() has its own re-entrancy guard, #3108, but the
            // UI should not invite the race.)
            isRestartingHost = true
            defer { isRestartingHost = false }
            do { try await backendService.start() } catch {
                pairingError = error.localizedDescription
            }
            loadAdvertisedSPKIPin()
        case .sharingNotStarted:
            hostingEnabled = true
            await applyHostingChanges()
        case .pinNotDerived:
            // Restart mints TLS material and re-derives the pin (applyHostingChanges
            // → backendService.start() → loadAdvertisedSPKIPin()).
            await applyHostingChanges()
            await refreshPairingCard()
        case .engineIsRemote, .addressMissing, .addressInsecure, .addressInvalid:
            break  // no button offered — see PairingBlocker.actionTitle
        }
    }

    private var sharedLibraryPath: String? {
        if let currentLibraryId = libraryManager.currentLibraryId,
           let library = libraryManager.getLibrary(id: currentLibraryId) {
            return library.url.path
        }
        return libraryManager.globalLibrary?.url.path
    }

    private func applyHostingChanges() async {
        isRestartingHost = true
        defer { isRestartingHost = false }

        if hostingEnabled {
            do {
                guard canHostRemoteAccess else {
                    pairingError = "Use the embedded engine on this Mac to host remotely."
                    return
                }
                _ = try validatedHostedRemoteURL(from: publicBaseURL)
            } catch {
                pairingError = error.localizedDescription
                return
            }
        } else {
            RemoteCertificatePinning.clearAdvertisedSPKIPin(hostString: publicBaseURL)
            RemoteCertificatePinning.clearPersistedSPKIPin(hostString: publicBaseURL)
            loadAdvertisedSPKIPin()
        }

        if backendService.isUsingExternalBackend {
            await appState.checkBackendHealth()
            appState.reconfigureGeneratedClientsForCurrentHost()
            libraryManager.reconfigureGeneratedClientsForCurrentHost()
            if hostingEnabled {
                await refreshPairedDevices()
            }
            return
        }

        backendService.stop()
        do {
            try await backendService.start()
            loadAdvertisedSPKIPin()
            await appState.checkBackendHealth()
            appState.reconfigureGeneratedClientsForCurrentHost()
            libraryManager.reconfigureGeneratedClientsForCurrentHost()
            if hostingEnabled {
                await refreshPairedDevices()
            }
        } catch {
            pairingError = error.localizedDescription
        }
    }

    private func refreshPairingCard() async {
        pairingError = nil
        pairingCode = nil

        guard pairingBlocker == nil else {
            return
        }

        isGeneratingPairingCode = true
        defer { isGeneratingPairingCode = false }

        do {
            try await Task.sleep(for: .milliseconds(200))
            try Task.checkCancellation()

            guard let ownerPairingService else {
                pairingError = "Use a reachable HTTPS URL to show the QR."
                return
            }
            let code = try await ownerPairingService.createPairingCode()
            pairingCode = code
        } catch {
            if error is CancellationError {
                return
            }
            pairingError = error.localizedDescription
        }
    }

    private func refreshPairedDevices() async {
        isLoadingDevices = true
        defer { isLoadingDevices = false }

        do {
            guard canHostRemoteAccess else {
                return
            }
            guard let ownerPairingService else {
                pairingError = "Use the embedded engine on this Mac to load devices."
                return
            }
            pairedDevices = try await ownerPairingService.listDevices()
        } catch {
            pairingError = error.localizedDescription
        }
    }

    private func revoke(deviceID: String) async {
        pairingError = nil
        do {
            guard canHostRemoteAccess else {
                return
            }
            guard let ownerPairingService else {
                pairingError = "Use the embedded engine on this Mac to revoke devices."
                return
            }
            try await ownerPairingService.revokeDevice(id: deviceID)
            await refreshPairedDevices()
        } catch {
            pairingError = error.localizedDescription
        }
    }

    private func loadAdvertisedSPKIPin() {
        spkiPin = RemoteAccessConfig.hostedBackendSPKIPin(hostString: publicBaseURL) ?? ""
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
}

func activePairedDevices(from devices: [PairedDeviceRecord]) -> [PairedDeviceRecord] {
    devices.filter { !$0.revoked }
}

/// Why the pairing card cannot show a QR, as a value rather than a lone string
/// (#3776/#3769). Each case carries its OWN headline — the card no longer prints
/// "Secure sharing needs HTTPS" over a stopped engine — and its own cure, so a
/// blocker is never a dead end. Non-negotiable: never a blank space, never a
/// dead control; if we cannot proceed, say why and offer the fix.
private enum PairingBlocker: Equatable {
    /// The library is served by an engine on ANOTHER machine, so this Mac has
    /// nothing to share. Nothing the app can do here — that is honest, not a dead end.
    case engineIsRemote
    /// The engine on this Mac is not running. The app can start it.
    case engineNotRunning
    /// Sharing has not been started yet. The app can start it — the user does not
    /// "enable a subsystem" first, they just share.
    case sharingNotStarted
    /// No reachable address for this Mac yet. The app cannot DISCOVER one today
    /// (there is no Bonjour/.local/Tailscale self-lookup — see #3776 comment), so
    /// this one honestly asks for it instead of pretending.
    case addressMissing
    case addressInsecure
    case addressInvalid(String)
    /// The SPKI pin could not be derived. This is the trap: the pin is computed,
    /// not typed, and the derivation is optional — a nil used to blank the card.
    /// Restarting the engine mints the TLS material and derives it.
    case pinNotDerived

    /// The headline. Each cause names ITSELF.
    var headline: String {
        switch self {
        case .engineIsRemote: return "This library is hosted on another machine"
        case .engineNotRunning: return "Fichero's engine isn't running"
        case .sharingNotStarted: return "Sharing hasn't started yet"
        case .addressMissing: return "Fichero needs this Mac's address"
        case .addressInsecure: return "Sharing needs HTTPS"
        case .addressInvalid: return "That address doesn't work"
        case .pinNotDerived: return "Fichero couldn't prepare the security certificate"
        }
    }

    var detail: String {
        switch self {
        case .engineIsRemote:
            return "Share This Mac works on the Mac that hosts the library. This one is connected to an engine elsewhere."
        case .engineNotRunning:
            return "The QR code needs a running engine to pair against."
        case .sharingNotStarted:
            return "Start sharing and Fichero will prepare the certificate and the invite for you."
        case .addressMissing:
            return "Enter the address other devices can reach this Mac on — an IP, a .local name, or a Tailscale hostname — under Advanced."
        case .addressInsecure:
            return "Devices pair over HTTPS so the connection can be pinned. Use an https:// address under Advanced."
        case .addressInvalid(let reason):
            return reason
        case .pinNotDerived:
            return "The certificate for this address hasn't been minted yet. Fichero can restart its engine and prepare it."
        }
    }

    /// The button — present ONLY where the app can genuinely perform the cure
    /// itself. nil where it honestly cannot (a remote engine; an address only the
    /// user knows), and then the detail says exactly what to do instead.
    var actionTitle: String? {
        switch self {
        case .engineNotRunning: return "Start Engine"
        case .sharingNotStarted: return "Start Sharing"
        case .pinNotDerived: return "Prepare Certificate"
        case .engineIsRemote, .addressMissing, .addressInsecure, .addressInvalid: return nil
        }
    }
}

private struct PairingCardView: View {
    let pairingCode: PairingCodeRecord?
    let qrCodeImage: PlatformImage?
    let publicURL: String?
    let inviteLink: String?
    let isGeneratingPairingCode: Bool
    let blocker: PairingBlocker?
    let errorMessage: String?
    let isResolving: Bool
    let onResolve: (PairingBlocker) -> Void
    let copiedInvite: Bool
    let onCopyInvite: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Show a QR code so iPhone, iPad, Vision Pro, or another Mac can connect to this library.")
                .font(.caption)
                .foregroundStyle(.secondary)

            if let pairingCode {
                VStack(alignment: .leading, spacing: 12) {
                    if let image = qrCodeImage {
                        Image(platformImage: image)
                            .interpolation(.none)
                            .resizable()
                            .frame(width: 180, height: 180)
                            .accessibilityLabel("Pairing QR code")
                    }

                    Text("Scan this with Fichero on another device.")
                        .font(.caption)
                        .foregroundStyle(.secondary)

                    if let publicURL {
                        LabeledContent("Address") {
                            Text(publicURL)
                                .textSelection(.enabled)
                        }
                        .font(.caption)
                    }

                    // The pairing link, as SELECTABLE TEXT (#3774). A QR is useless
                    // in the iOS Simulator — it has no camera — so manual entry is
                    // not a fallback there, it is the only way to pair. This is the
                    // exact same payload the QR encodes, produced by the same
                    // `RemoteClientPairing.inviteLinkString(from:)` the device's
                    // "Enter Link Manually" already parses: same SPKI pin, same
                    // one-time code, same expiry. Showing it changes convenience,
                    // not trust — the QR beside it already carries it.
                    if let inviteLink {
                        VStack(alignment: .leading, spacing: 4) {
                            Text("Pairing link")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                            Text(inviteLink)
                                .font(.system(.caption, design: .monospaced))
                                .textSelection(.enabled)
                                .lineLimit(3)
                                .truncationMode(.middle)
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .padding(6)
                                .background(Color(.textBackgroundColor))
                                .clipShape(RoundedRectangle(cornerRadius: 4))
                                .accessibilityLabel("Pairing link, selectable text")
                            Text("On the device: Enter Link Manually → paste this.")
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                        }
                    }

                    HStack {
                        if let inviteLink {
                            Button(copiedInvite ? "Pairing Link Copied" : "Copy Pairing Link", action: onCopyInvite)
                            if let shareURL = URL(string: inviteLink) {
                                ShareLink(item: shareURL) {
                                    Label("Share Link", systemImage: "square.and.arrow.up")
                                }
                            }
                        }
                    }
                    .buttonStyle(.bordered)

                    if inviteLink != nil {
                        Text("This link lets a device connect to your library — share only with people you trust.")
                            .font(.caption)
                            .foregroundStyle(.secondary)

                        // Saves the next person an hour (#3774): the Simulator runs on
                        // the Mac's own network stack, so the Mac's loopback engine is
                        // reachable from it directly. A real iPhone is a different
                        // machine — 127.0.0.1 there means the phone itself, so it must
                        // pair to this Mac's LAN address instead.
                        Text("iOS Simulator: it shares this Mac's network, so it can reach a local "
                             + "engine directly at https://127.0.0.1:8765. A real iPhone or iPad "
                             + "cannot — it needs this Mac's address above.")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }

                    Text("Expires \(pairingCode.expiresAt.formatted(date: .omitted, time: .shortened))")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            } else if isGeneratingPairingCode {
                ProgressView("Preparing QR code…")
            } else if let blocker {
                // Each cause states ITSELF and offers its cure. The old code printed
                // "Secure sharing needs HTTPS" over every blocker — so a stopped
                // engine was reported as an HTTPS problem, which is simply false.
                VStack(alignment: .leading, spacing: 6) {
                    Text(blocker.headline)
                        .font(.headline)
                    Text(blocker.detail)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    if let actionTitle = blocker.actionTitle {
                        Button(isResolving ? "Working…" : actionTitle) {
                            onResolve(blocker)
                        }
                        .buttonStyle(.borderedProminent)
                        .disabled(isResolving)
                    }
                    if let errorMessage {
                        Label(errorMessage, systemImage: "exclamationmark.triangle")
                            .font(.caption)
                            .foregroundStyle(.orange)
                    }
                }
            }
        }
        .padding(.vertical, 4)
    }
}
private struct PairedDevicesSectionView: View {
    let devices: [PairedDeviceRecord]
    let isLoading: Bool
    let canHostRemoteAccess: Bool
    let onRefresh: () -> Void
    let onRevoke: (String) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("Connected Devices")
                    .font(.headline)
                Spacer()
                Button(isLoading ? "Refreshing…" : "Refresh", action: onRefresh)
                    .disabled(isLoading || !canHostRemoteAccess)
                    .buttonStyle(.bordered)
            }

            if devices.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    Text("No devices have joined yet.")
                    Text("Devices that scan this QR will appear here.")
                }
                .font(.caption)
                .foregroundStyle(.secondary)
            } else {
                ForEach(devices) { device in
                    HStack(alignment: .top) {
                        VStack(alignment: .leading, spacing: 4) {
                            Text(device.name)
                            Text(device.lastSeen, style: .relative)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        Spacer()
                        Button("Remove") {
                            onRevoke(device.id)
                        }
                        .buttonStyle(.borderless)
                        .disabled(!canHostRemoteAccess)
                    }
                }
            }
        }
    }
}

private struct AdvancedRemoteAccessSection: View {
    @Binding var hostingEnabled: Bool
    @Binding var bonjourEnabled: Bool
    @Binding var publicBaseURL: String
    let canHostRemoteAccess: Bool
    let isRestartingHost: Bool
    let isRefreshingInvite: Bool
    let canResetInvite: Bool
    let onResetInvite: () -> Void
    let onApply: () -> Void

    var body: some View {
        DisclosureGroup("Advanced / Debug") {
            Toggle("Enable pairing and remote clients", isOn: $hostingEnabled)
            Toggle("Advertise this Mac on the local network", isOn: $bonjourEnabled)
                .disabled(!hostingEnabled)

            TextField("Reachable URL", text: $publicBaseURL)
                .textFieldStyle(.roundedBorder)
                .autocorrectionDisabled()
                .disabled(!hostingEnabled)

            Text(hostedRemoteAccessHelpText)
            .font(.caption)
            .foregroundStyle(.secondary)

            if hostingEnabled && !canHostRemoteAccess {
                Text("Use the embedded engine on this Mac to host remotely.")
                    .font(.caption)
                    .foregroundStyle(.red)
            }

            if hostingEnabled, canHostRemoteAccess {
                Button(isRefreshingInvite ? "Resetting Invite…" : "Reset Invite", action: onResetInvite)
                    .disabled(isRestartingHost || isRefreshingInvite || !canResetInvite)
            }

            Button(isRestartingHost ? "Applying..." : "Apply and Restart Engine", action: onApply)
                .disabled(isRestartingHost)
        }
    }
}
#endif
// swiftlint:enable file_length
