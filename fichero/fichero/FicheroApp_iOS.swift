#if canImport(UIKit) && !os(macOS)
import AVFoundation
import FicheroAPIClient
import OSLog
import SwiftUI
import UIKit
// swiftlint:disable file_length

@main
struct FicheroAppIOS: App {
    private let logger = Logger(subsystem: "app.fichero.fichero", category: "FicheroAppIOS")

    @StateObject private var backendService = EmbeddedBackendService()
    @StateObject private var appState = AppState()
    @StateObject private var viewSettings = ViewSettings()
    @StateObject private var libraryManager = LibraryManager.shared
    @StateObject private var windowState = WindowState(libraryId: LibraryManager.globalLibraryId)
    @StateObject private var claimFocusState = ClaimFocusState.shared
    @State private var kgFocusState = KGFocusState.shared
    @State private var executionObserver = WorkflowExecutionObserver()
    @StateObject private var captureQueue = MobileCaptureQueueStore()

    var body: some Scene {
        WindowGroup {
            FicheroSharedPlatformRoot(
                windowState: windowState,
                executionObserver: executionObserver
            )
                .environmentObject(windowState)
                .environmentObject(backendService)
                .environmentObject(appState)
                .environmentObject(viewSettings)
                .environmentObject(libraryManager)
                .environmentObject(claimFocusState)
                .environmentObject(appState.mcpService)
                .environmentObject(captureQueue)
                .environment(kgFocusState)
                .task {
                    await appState.checkBackendHealth()
                    if appState.isBackendRunning {
                        backendService.status = .running
                        backendService.errorMessage = nil
                        appState.startBackendHeartbeat()
                    } else {
                        backendService.status = .failed
                        backendService.errorMessage = appState.backendError
                        logger.error(
                            "External backend is not reachable at \(EngineConfig.host.absoluteString, privacy: .public)"
                        )
                        return
                    }

                    await KnownLibraryRegistryStore.shared.refresh()
                    await libraryManager.backendDidBecomeReady()
                    await captureQueue.resumePendingUploads(
                        using: MobileCaptureBackendUploadClient(libraryManager: libraryManager)
                    )
                }
        }
    }
}

private struct FicheroSharedPlatformRoot: View {
    @EnvironmentObject private var appState: AppState
    @EnvironmentObject private var libraryManager: LibraryManager
    @EnvironmentObject private var captureQueue: MobileCaptureQueueStore

    let windowState: WindowState
    let executionObserver: WorkflowExecutionObserver

    private var activeLibrary: LibraryManager.LibraryReference? {
        LibraryWorkspaceSelection.activeLibrary(
            currentLibraryId: libraryManager.currentLibraryId,
            windowLibraryId: windowState.libraryId,
            libraryManager: libraryManager
        )
    }

    var body: some View {
        Group {
            if appState.isCheckingBackend {
                ProgressView("Connecting to Fichero…")
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if !appState.isBackendRunning {
                RemoteConnectionSetupView {
                    await reconnectToConfiguredHost()
                }
            } else if let library = activeLibrary {
                LibraryWorkspaceRoot(
                    library: library,
                    windowState: windowState,
                    executionObserver: executionObserver
                )
                    .environmentObject(windowState)
                    .environmentObject(library.apiClient)
            } else {
                ContentUnavailableView(
                    "Library Unavailable",
                    systemImage: "externaldrive.badge.exclamationmark",
                    description: Text("Fichero could not load the Local library.")
                )
            }
        }
    }

    private func reconnectToConfiguredHost() async {
        await appState.checkBackendHealth()
        guard appState.isBackendRunning else { return }
        appState.startBackendHeartbeat()
        await KnownLibraryRegistryStore.shared.refresh()
        await libraryManager.backendDidBecomeReady()
        await captureQueue.resumePendingUploads(
            using: MobileCaptureBackendUploadClient(libraryManager: libraryManager)
        )
    }
}

private enum RemoteConnectionSheet: Identifiable {
    case scanner
    case captureQueue

    var id: Int {
        switch self {
        case .scanner:
            return 0
        case .captureQueue:
            return 1
        }
    }
}

// swiftlint:disable type_body_length
private struct RemoteConnectionSetupView: View {
    @EnvironmentObject private var appState: AppState
    @EnvironmentObject private var libraryManager: LibraryManager
    @EnvironmentObject private var captureQueue: MobileCaptureQueueStore

    let onConnected: @MainActor () async -> Void

    @StateObject private var discovery = BonjourDiscoveryService()
    @State private var detectedPayload: PairingQRCodePayload?
    @State private var presentedSheet: RemoteConnectionSheet?
    @State private var remoteURL = EngineConfig.usesCustomHost ? EngineConfig.hostString : ""
    @State private var pairCode = ""
    @State private var spkiPin = ""
    @State private var deviceName = RemoteClientPairing.defaultDeviceName()
    @State private var showAdvancedConnectionOptions = false
    @State private var isPairing = false
    @State private var errorMessage: String?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                VStack(alignment: .leading, spacing: 16) {
                    ZStack {
                        RoundedRectangle(cornerRadius: 28, style: .continuous)
                            .fill(
                                LinearGradient(
                                    colors: [
                                        Color.accentColor.opacity(0.20),
                                        Color.accentColor.opacity(0.06)
                                    ],
                                    startPoint: .topLeading,
                                    endPoint: .bottomTrailing
                                )
                            )

                        VStack(spacing: 12) {
                            Image(platformImage: hostIconImage)
                                .resizable()
                                .interpolation(.high)
                                .frame(width: 84, height: 84)

                            Label("Mac host", systemImage: "qrcode.viewfinder")
                                .font(.headline)
                                .padding(.horizontal, 14)
                                .padding(.vertical, 8)
                                .background(.thinMaterial, in: Capsule())
                        }
                        .foregroundStyle(Color.accentColor)
                    }
                    .frame(maxWidth: .infinity)
                    .frame(height: 200)

                    VStack(alignment: .leading, spacing: 8) {
                        Text("Connect to your Mac host")
                            .font(.largeTitle.weight(.semibold))
                        Text(
                            "Open Fichero on the Mac, enable Remote Access in Settings, and scan the QR code shown there."
                        )
                        .foregroundStyle(.secondary)
                    }
                }

                VStack(alignment: .leading, spacing: 12) {
                    Button {
                        if supportsCameraScanner {
                            presentedSheet = .scanner
                        } else {
                            showAdvancedConnectionOptions = true
                            errorMessage = "Camera scanning is unavailable on visionOS. Use the fallback URL/code section below."
                        }
                    } label: {
                        Label("Scan QR Code", systemImage: "qrcode.viewfinder")
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)

                    Text("Scan the QR shown in Fichero > Settings > Remote Access on the Mac.")
                        .font(.caption)
                        .foregroundStyle(.secondary)

                    Button {
                        presentedSheet = .captureQueue
                    } label: {
                        Label("Capture Photos", systemImage: "camera")
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.bordered)
                }

                if let detectedPayload {
                    GroupBox {
                        VStack(alignment: .leading, spacing: 8) {
                            Label("QR scanned", systemImage: "checkmark.circle.fill")
                                .font(.headline)
                            Text(
                                "This Mac host QR expires at \(detectedPayload.expiresAt.formatted(date: .omitted, time: .shortened))."
                            )
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                    }
                }

                DisclosureGroup("Fallback and debug options", isExpanded: $showAdvancedConnectionOptions) {
                    VStack(alignment: .leading, spacing: 16) {
                        Text("Use these options only if you cannot scan the QR code.")
                            .font(.caption)
                            .foregroundStyle(.secondary)

                        if !discovery.hosts.isEmpty {
                            VStack(alignment: .leading, spacing: 12) {
                                Text("Nearby Macs")
                                    .font(.headline)

                                ForEach(discovery.hosts) { host in
                                    VStack(alignment: .leading, spacing: 6) {
                                        HStack {
                                            Text(host.displayName)
                                                .font(.subheadline.weight(.semibold))
                                            if host.hasReachableURL {
                                                Spacer()
                                                Button("Use Host") {
                                                    if let reachableURL = host.reachableURL {
                                                        remoteURL = reachableURL
                                                    }
                                                }
                                                .buttonStyle(.bordered)
                                            }
                                        }

                                        if let reachableURL = host.reachableURL {
                                            Text(reachableURL)
                                                .font(.caption)
                                                .foregroundStyle(.secondary)
                                                .textSelection(.enabled)
                                        } else {
                                            Text("Open Fichero on that Mac, enable Remote Access, and scan its QR code there.")
                                                .font(.caption)
                                                .foregroundStyle(.secondary)
                                        }
                                    }
                                    .padding(12)
                                    .frame(maxWidth: .infinity, alignment: .leading)
                                    .background(Color.secondary.opacity(0.08), in: RoundedRectangle(cornerRadius: 12))
                                }
                            }
                        }

                        if let detectedPayload {
                            DisclosureGroup("Scanned connection details") {
                                VStack(alignment: .leading, spacing: 8) {
                                    LabeledContent("Host URL") {
                                        Text(detectedPayload.apiURL)
                                            .textSelection(.enabled)
                                    }
                                    LabeledContent("Pairing Code") {
                                        Text(detectedPayload.pairCode)
                                            .textSelection(.enabled)
                                    }
                                }
                                .font(.caption)
                                .foregroundStyle(.secondary)
                                .padding(.top, 4)
                            }
                        }

                        VStack(alignment: .leading, spacing: 12) {
                            Text("Manual URL / code")
                                .font(.headline)

                            TextField("Host URL", text: $remoteURL)
                                .textFieldStyle(.roundedBorder)
                                .textInputAutocapitalization(.never)
                                .autocorrectionDisabled()

                            TextField("Pairing Code", text: $pairCode)
                                .textFieldStyle(.roundedBorder)
                                .textInputAutocapitalization(.never)
                                .autocorrectionDisabled()

                            TextField("Certificate SPKI pin", text: $spkiPin)
                                .textFieldStyle(.roundedBorder)
                                .textInputAutocapitalization(.never)
                                .autocorrectionDisabled()

                            Text("The device name is assigned automatically.")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }

                        Button {
                            Task { await pairUsingAvailableInput() }
                        } label: {
                            Label("Connect", systemImage: "link")
                        }
                        .buttonStyle(.borderedProminent)
                        .disabled(isPairing || !canConnectWithCurrentInput)
                    }
                    .padding(.top, 4)
                }

                if let errorMessage {
                    Text(errorMessage)
                        .font(.caption)
                        .foregroundStyle(.red)
                }

                if let backendError = appState.backendError {
                    Text(backendError)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            .padding(24)
            .frame(maxWidth: 720, alignment: .leading)
        }
        .sheet(item: $presentedSheet) { sheet in
            switch sheet {
            case .scanner:
                QRCodeScannerSheet(
                    onCancel: { presentedSheet = nil },
                    onMessage: { message in
                        handleScannedMessage(message)
                        presentedSheet = nil
                    }
                )
            case .captureQueue:
                MobileCaptureQueueView(
                    queue: captureQueue,
                    retryPendingUploads: {
                        await captureQueue.resumePendingUploads(
                            using: MobileCaptureBackendUploadClient(libraryManager: libraryManager),
                            retryInterruptedUploads: true
                        )
                    }
                )
            }
        }
        .task {
            discovery.start()
        }
    }

    private var supportsCameraScanner: Bool {
        #if os(visionOS)
        return false
        #else
        return AVCaptureDevice.default(for: .video) != nil
        #endif
    }

    private var canConnectWithCurrentInput: Bool {
        !remoteURL.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            && !pairCode.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            && !spkiPin.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    private func handleScannedMessage(_ message: String) {
        do {
            let pairingFields = try RemoteClientPairing.pairingFields(from: message)
            let payload = try PairingQRCodePayloadDecoder.decode(message: message)
            detectedPayload = payload
            remoteURL = pairingFields.remoteURL
            pairCode = pairingFields.pairCode
            spkiPin = pairingFields.spkiPin
            errorMessage = nil
            Task { await pairUsingAvailableInput() }
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func pairUsingAvailableInput() async {
        isPairing = true
        errorMessage = nil
        defer { isPairing = false }

        do {
            let url = try await RemoteClientPairing.pairAndPersistHost(
                remoteURL: remoteURL,
                pairCode: pairCode,
                deviceName: deviceName,
                expectedSPKIPin: spkiPin
            )
            appState.reconfigureGeneratedClientsForCurrentHost()
            libraryManager.reconfigureGeneratedClientsForCurrentHost()
            await onConnected()
            if !appState.isBackendRunning {
                errorMessage = "Paired successfully, but the host is not responding yet."
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private var hostIconImage: PlatformImage {
        if let resourcePath = Bundle.main.resourcePath {
            let iconPath = "\(resourcePath)/Fichero Engine.app/Contents/Resources/engine.icns"
            if let image = PlatformImage(contentsOfFile: iconPath) {
                return image
            }
        }
        #if canImport(AppKit)
        return PlatformImage(systemSymbolName: "server.rack", accessibilityDescription: nil) ?? PlatformImage()
        #elseif canImport(UIKit)
        return PlatformImage(systemName: "server.rack") ?? PlatformImage()
        #else
        return PlatformImage()
        #endif
    }
}
// swiftlint:enable type_body_length

private struct QRCodeScannerSheet: View {
    let onCancel: () -> Void
    let onMessage: (String) -> Void

    @State private var errorMessage: String?

    var body: some View {
        NavigationStack {
            VStack(spacing: 16) {
                Text("Open Fichero on the Mac, open Settings > Remote Access, and scan the QR code shown there.")
                    .font(.headline)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal)

                #if os(visionOS)
                VStack(spacing: 12) {
                    Image(systemName: "qrcode.viewfinder")
                        .font(.largeTitle)
                    Text("Camera QR scanning is unavailable on visionOS. Use the manual URL/code section below.")
                        .multilineTextAlignment(.center)
                        .foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity, minHeight: 320)
                .padding()
                .background(Color.secondary.opacity(0.08), in: RoundedRectangle(cornerRadius: 20))
                #else
                QRCodeScannerView(
                    onMessage: onMessage,
                    onFailure: { message in
                        errorMessage = message
                    }
                )
                .frame(minHeight: 320)
                .clipShape(RoundedRectangle(cornerRadius: 20))
                .overlay(
                    RoundedRectangle(cornerRadius: 20)
                        .stroke(Color.secondary.opacity(0.3), lineWidth: 1)
                )
                #endif

                if let errorMessage {
                    Text(errorMessage)
                        .font(.caption)
                        .foregroundStyle(.red)
                        .multilineTextAlignment(.center)
                        .padding(.horizontal)
                }
            }
            .padding()
            .navigationTitle("Scan QR Code")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel", action: onCancel)
                }
            }
        }
    }
}

#if !os(visionOS)
private struct QRCodeScannerView: UIViewControllerRepresentable {
    let onMessage: (String) -> Void
    let onFailure: (String) -> Void

    func makeCoordinator() -> Coordinator {
        Coordinator(onMessage: onMessage, onFailure: onFailure)
    }

    func makeUIViewController(context: Context) -> ScannerViewController {
        let controller = ScannerViewController()
        controller.coordinator = context.coordinator
        return controller
    }

    func updateUIViewController(_ uiViewController: ScannerViewController, context: Context) {}

    final class Coordinator: NSObject, AVCaptureMetadataOutputObjectsDelegate {
        private let onMessage: (String) -> Void
        private let onFailure: (String) -> Void
        private var hasCompleted = false

        init(onMessage: @escaping (String) -> Void, onFailure: @escaping (String) -> Void) {
            self.onMessage = onMessage
            self.onFailure = onFailure
        }

        func metadataOutput(
            _ output: AVCaptureMetadataOutput,
            didOutput metadataObjects: [AVMetadataObject],
            from connection: AVCaptureConnection
        ) {
            guard !hasCompleted else { return }
            guard let message = metadataObjects
                .compactMap({ $0 as? AVMetadataMachineReadableCodeObject })
                .first(where: { $0.type == .qr })?
                .stringValue else {
                return
            }
            hasCompleted = true
            onMessage(message)
        }

        func fail(_ message: String) {
            guard !hasCompleted else { return }
            onFailure(message)
        }
    }

    final class ScannerViewController: UIViewController {
        var coordinator: Coordinator?

        private let session = AVCaptureSession()
        private var previewLayer: AVCaptureVideoPreviewLayer?

        override func viewDidLoad() {
            super.viewDidLoad()
            view.backgroundColor = .black
            configureSession()
        }

        override func viewDidLayoutSubviews() {
            super.viewDidLayoutSubviews()
            previewLayer?.frame = view.bounds
        }

        override func viewWillAppear(_ animated: Bool) {
            super.viewWillAppear(animated)
            if !session.isRunning {
                session.startRunning()
            }
        }

        override func viewWillDisappear(_ animated: Bool) {
            super.viewWillDisappear(animated)
            if session.isRunning {
                session.stopRunning()
            }
        }

        private func configureSession() {
            guard let device = AVCaptureDevice.default(for: .video) else {
                coordinator?.fail("This device does not have a camera available for QR scanning.")
                return
            }

            do {
                let input = try AVCaptureDeviceInput(device: device)
                guard session.canAddInput(input) else {
                    coordinator?.fail("Fichero could not access the camera input.")
                    return
                }
                session.addInput(input)

                let output = AVCaptureMetadataOutput()
                guard session.canAddOutput(output) else {
                    coordinator?.fail("Fichero could not configure QR scanning.")
                    return
                }
                session.addOutput(output)
                output.setMetadataObjectsDelegate(coordinator, queue: .main)
                output.metadataObjectTypes = [.qr]

                let previewLayer = AVCaptureVideoPreviewLayer(session: session)
                previewLayer.videoGravity = .resizeAspectFill
                previewLayer.frame = view.bounds
                view.layer.addSublayer(previewLayer)
                self.previewLayer = previewLayer
            } catch {
                coordinator?.fail("Camera setup failed: \(error.localizedDescription)")
            }
        }
    }
}
#endif

private struct BonjourHostRecord: Identifiable, Equatable {
    let id: String
    let displayName: String
    let reachableURL: String?

    var hasReachableURL: Bool {
        guard let reachableURL else { return false }
        return !reachableURL.isEmpty
    }
}

private final class BonjourDiscoveryService: NSObject, ObservableObject {
    @Published private(set) var hosts: [BonjourHostRecord] = []

    private let browser = NetServiceBrowser()
    private var services: [String: NetService] = [:]
    private var records: [String: BonjourHostRecord] = [:]
    private var started = false

    override init() {
        super.init()
        browser.delegate = self
    }

    func start() {
        guard !started else { return }
        started = true
        browser.searchForServices(ofType: "_fichero._tcp.", inDomain: "local.")
    }

    private func refreshHosts() {
        hosts = records.values.sorted { $0.displayName.localizedCaseInsensitiveCompare($1.displayName) == .orderedAscending }
    }

    private func recordID(for service: NetService) -> String {
        "\(service.domain)|\(service.type)|\(service.name)"
    }

    private func decodeTXTRecord(for service: NetService) -> [String: String] {
        guard let txtData = service.txtRecordData() else { return [:] }
        return NetService.dictionary(fromTXTRecord: txtData).reduce(into: [:]) { partialResult, pair in
            partialResult[pair.key] = String(data: pair.value, encoding: .utf8) ?? ""
        }
    }

    private func handleFound(_ service: NetService, moreComing: Bool) {
        let id = recordID(for: service)
        services[id] = service
        service.delegate = self
        service.resolve(withTimeout: 5)

        records[id] = BonjourHostRecord(
            id: id,
            displayName: service.name,
            reachableURL: nil
        )
        if !moreComing {
            refreshHosts()
        }
    }

    private func handleRemoved(_ service: NetService, moreComing: Bool) {
        let id = recordID(for: service)
        services[id] = nil
        records[id] = nil
        if !moreComing {
            refreshHosts()
        }
    }

    private func handleResolved(_ sender: NetService) {
        let id = recordID(for: sender)
        let txtRecord = decodeTXTRecord(for: sender)
        let reachableURL = txtRecord["public_url"]
            .flatMap {
                try? validatedRemoteURL(
                    from: $0,
                    allowLocalhost: false,
                    requireSecureTransportForRemote: true
                ).absoluteString
            }
        records[id] = BonjourHostRecord(
            id: id,
            displayName: sender.name,
            reachableURL: reachableURL
        )
        refreshHosts()
    }

    private func handleResolveFailure(_ sender: NetService) {
        let id = recordID(for: sender)
        records[id] = BonjourHostRecord(
            id: id,
            displayName: sender.name,
            reachableURL: nil
        )
        refreshHosts()
    }
}

extension BonjourDiscoveryService: NetServiceBrowserDelegate {
    func netServiceBrowser(
        _ browser: NetServiceBrowser,
        didFind service: NetService,
        moreComing: Bool
    ) {
        handleFound(service, moreComing: moreComing)
    }

    func netServiceBrowser(
        _ browser: NetServiceBrowser,
        didRemove service: NetService,
        moreComing: Bool
    ) {
        handleRemoved(service, moreComing: moreComing)
    }
}

extension BonjourDiscoveryService: NetServiceDelegate {
    func netServiceDidResolveAddress(_ sender: NetService) {
        handleResolved(sender)
    }

    func netService(_ sender: NetService, didNotResolve errorDict: [String: NSNumber]) {
        handleResolveFailure(sender)
    }
}
#endif
