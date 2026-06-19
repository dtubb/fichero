import CoreImage
import CoreImage.CIFilterBuiltins
import FicheroAPIClient
import SwiftUI

// MARK: - Backend Settings

// Backend connection settings
// swiftlint:disable:next type_body_length
struct BackendSettingsView: View {
    @EnvironmentObject var appState: AppState
    @EnvironmentObject var backendService: EmbeddedBackendService
    // storageService is per-LIBRARY, not in the Settings scene environment — reach it
    // optionally via libraryManager (which IS injected here). A required @EnvironmentObject
    // would trap "No ObservableObject of type StorageServiceGenerated" and crash this tab.
    @EnvironmentObject var libraryManager: LibraryManager
    @AppStorage(EngineConfig.userDefaultsKey) private var engineHost = EngineConfig.defaultHostString
    @AppStorage(RemoteAccessConfig.hostingEnabledKey) private var hostingEnabled = false
    @AppStorage(RemoteAccessConfig.bonjourEnabledKey) private var bonjourEnabled = false
    @AppStorage(RemoteAccessConfig.publicBaseURLKey) private var publicBaseURL = ""

    @State private var storageStats: StorageStats?
    @State private var isLoadingStats = false
    @State private var statsError: String?
    @State private var pairingCode: PairingCodeRecord?
    @State private var pairedDevices: [PairedDeviceRecord] = []
    @State private var pairingError: String?
    @State private var isRestartingHost = false
    @State private var isGeneratingPairingCode = false
    @State private var isLoadingDevices = false
    @State private var spkiPin = ""

    private let qrContext = CIContext()

    var body: some View {
        Form {
            Section("Connection") {
                TextField("Engine URL", text: $engineHost)
                    .textFieldStyle(.roundedBorder)
                    .autocorrectionDisabled()

                LabeledContent("Effective API Base") {
                    Text(EngineConfig.apiBaseURL.absoluteString)
                        .foregroundStyle(.secondary)
                        .textSelection(.enabled)
                }

                Text("Leave blank to use the embedded localhost engine.")
                    .font(.caption)
                    .foregroundStyle(.secondary)

                HStack {
                    Circle()
                        .fill(appState.isBackendRunning ? Color.green : Color.red)
                        .frame(width: 10, height: 10)

                    Text(appState.isBackendRunning ? "Connected" : "Disconnected")

                    Spacer()
                }
            }

            #if canImport(AppKit)
            MacRemoteClientPairingSection()
            #endif

            #if canImport(AppKit)
            Section("Remote Access") {
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
                    Text("Remote Access hosting requires the embedded local engine. Clear Engine URL to host from this Mac.")
                        .font(.caption)
                        .foregroundStyle(.red)
                }

                HStack {
                    Button(isRestartingHost ? "Applying..." : "Apply and Restart Engine") {
                        Task { await applyHostingChanges() }
                    }
                    .disabled(isRestartingHost)

                    Button(isGeneratingPairingCode ? "Generating..." : "Generate Pairing QR") {
                        Task { await generatePairingQRCode() }
                    }
                    .disabled(
                        isGeneratingPairingCode
                            || !hostingEnabled
                            || !hasValidReachableURL
                            || !hasValidSPKIPin
                            || !appState.isBackendRunning
                    )

                    Button(isLoadingDevices ? "Refreshing..." : "Refresh Devices") {
                        Task { await refreshPairedDevices() }
                    }
                    .disabled(isLoadingDevices || !hostingEnabled || !appState.isBackendRunning || !canHostRemoteAccess)
                }

                if let pairingError {
                    Text(pairingError)
                        .font(.caption)
                        .foregroundStyle(.red)
                }

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
                    .padding(.vertical, 4)
                }

                if canHostRemoteAccess && !pairedDevices.isEmpty {
                    ForEach(pairedDevices) { device in
                        HStack(alignment: .top) {
                            VStack(alignment: .leading, spacing: 4) {
                                Text(device.name)
                                Text(device.lastSeen, style: .relative)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                            Spacer()
                            Button("Revoke") {
                                Task { await revoke(deviceID: device.id) }
                            }
                            .buttonStyle(.borderless)
                            .disabled(!canHostRemoteAccess)
                        }
                    }
                }
            }
            #endif

            Section("Statistics") {
                LabeledContent("Documents") {
                    Text("\(appState.documentCount)")
                }
                LabeledContent("Indexed") {
                    Text("\(appState.indexedCount)")
                }

                if isLoadingStats {
                    LabeledContent("Storage") {
                        ProgressView()
                            .controlSize(.small)
                    }
                } else if let error = statsError {
                    LabeledContent("Storage") {
                        Text(error)
                            .foregroundStyle(.red)
                            .font(.caption)
                    }
                } else if let stats = storageStats {
                    LabeledContent("Total Size") {
                        Text(ByteCountFormatter.string(fromByteCount: stats.totalSize, countStyle: .file))
                    }
                    LabeledContent("Files") {
                        Text("\(stats.fileCount)")
                    }
                    LabeledContent("Collections") {
                        Text("\(stats.collectionCount)")
                    }
                    LabeledContent("Linked Files") {
                        Text("\(stats.linkedCount)")
                    }
                    LabeledContent("Copied Files") {
                        Text("\(stats.copiedCount)")
                    }
                }
            }
        }
        .formStyle(.grouped)
        .task {
            loadAdvertisedSPKIPin()
            await loadStorageStats()
            #if canImport(AppKit)
            if !canHostRemoteAccess {
                pairedDevices = []
            }
            if hostingEnabled, appState.isBackendRunning, canHostRemoteAccess {
                await refreshPairedDevices()
            }
            #endif
        }
        .onChange(of: publicBaseURL) { _, _ in
            loadAdvertisedSPKIPin()
        }
    }

    // MARK: - Private

    private func loadStorageStats() async {
        isLoadingStats = true
        statsError = nil
        defer { isLoadingStats = false }
        guard let storageService = libraryManager.globalLibrary?.storageService else {
            // No library open → no per-library storage stats to show.
            storageStats = nil
            return
        }
        do {
            storageStats = try await storageService.getStats()
        } catch {
            statsError = error.localizedDescription
        }
    }

    #if canImport(AppKit)
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

    private var hasValidReachableURL: Bool {
        (try? validatedReachableURL()) != nil
    }

    private var hasValidSPKIPin: Bool {
        (try? RemoteCertificatePinning.validatedSPKIPin(spkiPin)) != nil
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

    private func applyHostingChanges() async {
        isRestartingHost = true
        pairingError = nil
        defer { isRestartingHost = false }

        if hostingEnabled {
            do {
                guard canHostRemoteAccess else {
                    pairingError = "Remote Access hosting requires the embedded local engine. Clear Engine URL to host from this Mac."
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

    private func generatePairingQRCode() async {
        isGeneratingPairingCode = true
        pairingError = nil
        defer { isGeneratingPairingCode = false }

        do {
            guard canHostRemoteAccess else {
                pairingError = "Remote Access hosting requires the embedded local engine. Clear Engine URL to host from this Mac."
                return
            }
            _ = try validatedReachableURL()
            let normalizedSPKIPin = try RemoteCertificatePinning.validatedSPKIPin(spkiPin)
            guard let ownerPairingService else {
                pairingError = "Set a reachable private URL before generating a pairing QR code."
                return
            }
            let code = try await ownerPairingService.createPairingCode()
            pairingCode = code
            _ = advertisedPairingService?.buildQRCodePayload(from: code, spki: normalizedSPKIPin)
            await refreshPairedDevices()
        } catch {
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
                pairingError = "Remote Access hosting requires the embedded local engine. Clear Engine URL to host from this Mac."
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
                pairingError = "Remote Access hosting requires the embedded local engine. Clear Engine URL to host from this Mac."
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
    #endif
}
