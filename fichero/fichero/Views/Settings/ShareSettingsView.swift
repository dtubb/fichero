#if canImport(AppKit)
import CoreImage
import CoreImage.CIFilterBuiltins
import FicheroAPIClient
import SwiftUI

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

                if hostingEnabled {
                    qrOrStatusContent
                }
            }

            if !activePairedDevices(from: pairedDevices).isEmpty {
                Section("Connected Devices") {
                    ForEach(activePairedDevices(from: pairedDevices)) { device in
                        HStack {
                            VStack(alignment: .leading, spacing: 2) {
                                Text(device.name)
                                Text(device.lastSeen, style: .relative)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                            Spacer()
                            Button("Remove") {
                                Task { await revoke(deviceID: device.id) }
                            }
                            .buttonStyle(.borderless)
                        }
                    }
                }
            }

        }
        .formStyle(.grouped)
        .task {
            loadSPKIPin()
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
        .onChange(of: publicBaseURL) { _, _ in loadSPKIPin() }
    }

    // MARK: - QR / Status

    @ViewBuilder
    private var qrOrStatusContent: some View {
        if let pairingCode, let qrImage = makeQRImage(for: pairingCode) {
            HStack {
                Spacer(minLength: 0)
                VStack(alignment: .center, spacing: 12) {
                    Image(platformImage: qrImage)
                        .interpolation(.none)
                        .resizable()
                        .frame(width: 220, height: 220)
                        .accessibilityLabel("Pairing QR code")

                    Text("Scan this QR Code with Fichero on another device to connect.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)

                    DisclosureGroup("Show Details") {
                        LabeledContent("Address") {
                            Text(displayAddress)
                                .textSelection(.enabled)
                                .font(.caption.monospaced())
                        }
                        LabeledContent("Route") {
                            Text(displayRoute)
                        }
                        LabeledContent("Code") {
                            Text(formatCode(pairingCode.code))
                                .textSelection(.enabled)
                                .font(.caption.monospaced())
                        }
                    }
                    .font(.caption)
                }
                Spacer(minLength: 0)
            }
            .padding(.vertical, 4)
        } else if isGeneratingCode {
            ProgressView("Preparing QR code…")
        } else {
            Text(statusMessage)
                .font(.caption)
                .foregroundStyle(.secondary)
        }

        if let shareError {
            Text(shareError)
                .font(.caption)
                .foregroundStyle(.red)
        }
    }

    private var statusMessage: String {
        guard EngineConfig.engineIsLocal else {
            return "Sharing works when Fichero is running on this Mac."
        }
        guard appState.isBackendRunning else {
            return "Fichero is not connected on this Mac right now."
        }
        let url = publicBaseURL.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !url.isEmpty else {
            return "Setting up secure sharing…"
        }
        guard (try? RemoteCertificatePinning.validatedSPKIPin(spkiPin)) != nil else {
            return "Applying certificate. Toggle sharing off and on if this persists."
        }
        return "Preparing…"
    }

    private var displayAddress: String {
        let url = publicBaseURL.trimmingCharacters(in: .whitespacesAndNewlines)
        return url.isEmpty ? EngineConfig.apiBaseURL.absoluteString : url
    }

    private var displayRoute: String {
        let addr = displayAddress.lowercased()
        if addr.contains(".local") || addr.contains("localhost") || addr.contains("127.0.0.1") {
            return "Same Network"
        }
        return "Custom"
    }

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

    private func formatCode(_ code: String) -> String {
        let chars = code.filter { $0.isNumber || $0.isLetter }
        guard chars.count >= 4 else { return code }
        let mid = chars.index(chars.startIndex, offsetBy: chars.count / 2)
        return "\(chars[..<mid]) \(chars[mid...])"
    }

    // MARK: - QR generation

    private func makeQRImage(for record: PairingCodeRecord) -> PlatformImage? {
        guard let publicURL = try? validatedHostedRemoteURL(from: publicBaseURL) else { return nil }
        guard let normalizedPin = try? RemoteCertificatePinning.validatedSPKIPin(spkiPin) else { return nil }
        let service = PairingService(apiRoot: publicURL)
        let payload = service.buildQRCodePayload(
            from: record,
            spki: normalizedPin,
            libraryPath: sharedLibraryPath
        )
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        guard let data = try? encoder.encode(payload) else { return nil }
        let filter = CIFilter.qrCodeGenerator()
        filter.message = data
        filter.correctionLevel = "M"
        guard let output = filter.outputImage?.transformed(by: CGAffineTransform(scaleX: 12, y: 12)),
              let cgImage = qrContext.createCGImage(output, from: output.extent) else { return nil }
        return PlatformImage(cgImage: cgImage, size: .zero)
    }

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
            if hostingEnabled {
                await refreshDevices()
            }
            return
        }

        backendService.stop()
        do {
            try await backendService.start()
            loadSPKIPin()
            await appState.checkBackendHealth()
            appState.reconfigureGeneratedClientsForCurrentHost()
            libraryManager.reconfigureGeneratedClientsForCurrentHost()
            if hostingEnabled { await refreshDevices() }
        } catch {
            shareError = error.localizedDescription
        }
    }

    private func refreshPairingCode() async {
        pairingCode = nil
        shareError = nil
        guard EngineConfig.engineIsLocal,
              appState.isBackendRunning,
              hostingEnabled,
              (try? validatedHostedRemoteURL(from: publicBaseURL)) != nil,
              (try? RemoteCertificatePinning.validatedSPKIPin(spkiPin)) != nil
        else { return }
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
