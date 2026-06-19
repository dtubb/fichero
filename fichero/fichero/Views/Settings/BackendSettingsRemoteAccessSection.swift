#if canImport(AppKit)
import CoreImage
import CoreImage.CIFilterBuiltins
import FicheroAPIClient
import SwiftUI

struct BackendSettingsRemoteAccessSection: View {
    @EnvironmentObject private var appState: AppState
    @EnvironmentObject private var backendService: EmbeddedBackendService
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

    private let qrContext = CIContext()

    var body: some View {
        Section("Remote Access") {
            PairingCardView(
                pairingCode: pairingCode,
                qrCodeImage: qrCodeImage,
                isGeneratingPairingCode: isGeneratingPairingCode,
                statusMessage: pairingStatusMessage ?? pairingError
            )

            if canHostRemoteAccess {
                PairedDevicesSectionView(
                    devices: activePairedDevices(from: pairedDevices),
                    isLoading: isLoadingDevices,
                    canHostRemoteAccess: canHostRemoteAccess,
                    onRefresh: { Task { await refreshPairedDevices() } },
                    onRevoke: { deviceID in Task { await revoke(deviceID: deviceID) } }
                )
            }

            AdvancedRemoteAccessSection(
                hostingEnabled: $hostingEnabled,
                bonjourEnabled: $bonjourEnabled,
                publicBaseURL: $publicBaseURL,
                spkiPin: $spkiPin,
                canHostRemoteAccess: canHostRemoteAccess,
                isRestartingHost: isRestartingHost,
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
        guard let publicURL = try? validatedReachableURL() else { return nil }
        return PairingService(apiRoot: publicURL)
    }

    private var hasValidSPKIPin: Bool {
        (try? RemoteCertificatePinning.validatedSPKIPin(spkiPin)) != nil
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

    private var qrCodeImage: PlatformImage? {
        guard let pairingCode, let advertisedPairingService else { return nil }
        guard let normalizedSPKIPin = try? RemoteCertificatePinning.validatedSPKIPin(spkiPin) else {
            return nil
        }

        let payload = advertisedPairingService.buildQRCodePayload(from: pairingCode, spki: normalizedSPKIPin)
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
        guard hostingEnabled else {
            return "Turn on Remote Access in Advanced / Debug."
        }
        guard canHostRemoteAccess else {
            return "Use the embedded engine on this Mac."
        }
        guard appState.isBackendRunning else {
            return "Start the embedded engine."
        }

        do {
            _ = try validatedReachableURL()
        } catch let error as RemoteURLValidationError {
            switch error {
            case .blank:
                return "Use an HTTPS reachable URL."
            case .insecureRemoteTransport:
                return error.localizedDescription
            default:
                return error.localizedDescription
            }
        } catch {
            return error.localizedDescription
        }

        guard hasValidSPKIPin else {
            return "Add the host's SPKI pin."
        }
        return nil
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
                _ = try validatedReachableURL()
                let normalizedSPKIPin = try RemoteCertificatePinning.validatedSPKIPin(spkiPin)
                try RemoteCertificatePinning.persistAdvertisedSPKIPin(
                    normalizedSPKIPin,
                    hostString: publicBaseURL
                )
            } catch {
                pairingError = error.localizedDescription
                return
            }
        } else {
            RemoteCertificatePinning.clearAdvertisedSPKIPin(hostString: publicBaseURL)
        }

        backendService.stop()
        do {
            try await backendService.start()
            await appState.checkBackendHealth()
            appState.reconfigureGeneratedClientsForCurrentHost()
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

    private func validatedReachableURL() throws -> URL {
        try validatedRemoteURL(from: publicBaseURL, allowLocalhost: false, requireSecureTransportForRemote: true)
    }

    private func loadAdvertisedSPKIPin() {
        spkiPin = RemoteCertificatePinning.advertisedSPKIPin(hostString: publicBaseURL) ?? ""
    }
}

func activePairedDevices(from devices: [PairedDeviceRecord]) -> [PairedDeviceRecord] {
    devices.filter { !$0.revoked }
}

private struct PairingCardView: View {
    let pairingCode: PairingCodeRecord?
    let qrCodeImage: PlatformImage?
    let isGeneratingPairingCode: Bool
    let statusMessage: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Pair a Device")
                .font(.headline)

            Text("The pairing QR appears here when Remote Access is ready.")
                .font(.caption)
                .foregroundStyle(.secondary)

            if let pairingCode {
                VStack(alignment: .leading, spacing: 10) {
                    if let image = qrCodeImage {
                        Image(platformImage: image)
                            .interpolation(.none)
                            .resizable()
                            .frame(width: 180, height: 180)
                            .accessibilityLabel("Pairing QR code")
                    }

                    Text(pairingCode.code)
                        .font(.system(.title3, design: .monospaced))
                        .textSelection(.enabled)

                    Text("Expires \(pairingCode.expiresAt.formatted(date: .omitted, time: .shortened))")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            } else if isGeneratingPairingCode {
                ProgressView("Preparing pairing QR...")
            } else if let statusMessage {
                Text(statusMessage)
                    .font(.caption)
                    .foregroundStyle(.red)
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
        Divider()
        HStack {
            Text("Paired Devices")
                .font(.headline)
            Spacer()
            Button(isLoading ? "Refreshing..." : "Refresh Devices", action: onRefresh)
                .disabled(isLoading || !canHostRemoteAccess)
        }

        if devices.isEmpty {
            Text("No active paired devices.")
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
                    Button("Revoke") {
                        onRevoke(device.id)
                    }
                    .buttonStyle(.borderless)
                    .disabled(!canHostRemoteAccess)
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

            Text(
                "Use a private reachable URL such as your Tailscale HTTPS address. "
                    + "Bonjour only announces that this Mac is available; the QR code "
                    + "still carries the URL the client should call."
            )
            .font(.caption)
            .foregroundStyle(.secondary)

            if hostingEnabled && !canHostRemoteAccess {
                Text("Use the embedded engine on this Mac to host remotely.")
                    .font(.caption)
                    .foregroundStyle(.red)
            }

            Button(isRestartingHost ? "Applying..." : "Apply and Restart Engine", action: onApply)
                .disabled(isRestartingHost)
        }
    }
}
#endif
