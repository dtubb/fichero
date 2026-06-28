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
    @ObservedObject private var appState: AppState
    @ObservedObject private var backendService: EmbeddedBackendService
    @ObservedObject private var libraryManager: LibraryManager
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
        self._appState = ObservedObject(wrappedValue: appState)
        self._backendService = ObservedObject(wrappedValue: backendService)
        self._libraryManager = ObservedObject(wrappedValue: libraryManager)
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
                statusMessage: pairingStatusMessage ?? pairingError,
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
                spkiPin: $spkiPin,
                canHostRemoteAccess: canHostRemoteAccess,
                isRestartingHost: isRestartingHost,
                isRefreshingInvite: isGeneratingPairingCode,
                canResetInvite: pairingStatusMessage == nil,
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

    private var pairingStatusMessage: String? {
        guard canHostRemoteAccess else {
            return "Share This Mac works when Fichero is running on this Mac."
        }
        guard appState.isBackendRunning else {
            return "Fichero is not connected on this Mac right now."
        }
        guard hostingEnabled else {
            return "Set up secure sharing, then Fichero can show a QR code here."
        }

        do {
            _ = try validatedHostedRemoteURL(from: publicBaseURL)
        } catch let error as RemoteURLValidationError {
            switch error {
            case .blank:
                return "Set up secure sharing, then Fichero can show a QR code here."
            case .insecureRemoteTransport:
                return "Set up secure sharing, then Fichero can show a QR code here."
            default:
                return error.localizedDescription
            }
        } catch {
            return error.localizedDescription
        }

        guard hasValidSPKIPin else {
            return "Finish secure sharing setup in Advanced, then Fichero can show a QR code here."
        }
        return nil
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

        guard pairingStatusMessage == nil else {
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
        spkiPin = RemoteCertificatePinning.advertisedSPKIPin(hostString: publicBaseURL) ?? ""
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

private struct PairingCardView: View {
    let pairingCode: PairingCodeRecord?
    let qrCodeImage: PlatformImage?
    let publicURL: String?
    let inviteLink: String?
    let isGeneratingPairingCode: Bool
    let statusMessage: String?
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

                    HStack {
                        if let inviteLink {
                            Button(copiedInvite ? "Invite Copied" : "Copy Invite", action: onCopyInvite)
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
                    }

                    Text("Expires \(pairingCode.expiresAt.formatted(date: .omitted, time: .shortened))")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            } else if isGeneratingPairingCode {
                ProgressView("Preparing QR code…")
            } else if let statusMessage {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Secure sharing needs HTTPS.")
                        .font(.headline)
                    Text(statusMessage)
                        .font(.caption)
                        .foregroundStyle(.secondary)
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
    @Binding var spkiPin: String
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

            TextField("Certificate SPKI pin", text: $spkiPin)
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
