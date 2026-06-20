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

private enum DeviceEntryPhase {
    case connect
    case signingIn(PairingQRCodePayload)
    case capture
}

private struct RemoteConnectionSetupView: View {
    @EnvironmentObject private var appState: AppState
    @EnvironmentObject private var libraryManager: LibraryManager
    @EnvironmentObject private var captureQueue: MobileCaptureQueueStore

    let onConnected: @MainActor () async -> Void

    @State private var phase: DeviceEntryPhase = .connect
    @State private var showingScanner = false
    @State private var username = ""
    @State private var password = ""
    @State private var isPairing = false
    @State private var errorMessage: String?
    @State private var pickerSource: CaptureSource?
    @State private var captureError: String?

    var body: some View {
        Group {
            switch phase {
            case .connect:
                connectView
            case .signingIn(let payload):
                signInView(payload: payload)
            case .capture:
                captureView
            }
        }
        .sheet(isPresented: $showingScanner) {
            QRCodeScannerSheet(
                onCancel: { showingScanner = false },
                onMessage: { message in
                    handleScannedMessage(message)
                    showingScanner = false
                }
            )
        }
        .sheet(item: $pickerSource) { source in
            MobileCaptureImagePicker(
                sourceType: source.sourceType,
                onImage: { image in handleCapturedImage(image, source: source) },
                onCancel: { pickerSource = nil }
            )
        }
    }

    // MARK: — Connect

    private var connectView: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                Text("Connect to Fichero on Mac")
                    .font(.largeTitle.bold())

                VStack(spacing: 14) {
                    ZStack {
                        RoundedRectangle(cornerRadius: 22)
                            .fill(Color.accentColor.opacity(0.08))
                            .overlay(
                                RoundedRectangle(cornerRadius: 22)
                                    .stroke(Color.accentColor.opacity(0.18), lineWidth: 1)
                            )
                        Image(systemName: "qrcode.viewfinder")
                            .font(.system(size: 64))
                            .foregroundStyle(Color.accentColor.opacity(0.45))
                    }
                    .frame(height: 220)

                    Button {
                        if supportsCameraScanner {
                            showingScanner = true
                        } else {
                            errorMessage = "Camera scanning is unavailable on this device."
                        }
                    } label: {
                        Label("Scan QR Code", systemImage: "qrcode.viewfinder")
                            .frame(maxWidth: .infinity, minHeight: 46)
                    }
                    .buttonStyle(.borderedProminent)

                    Button { phase = .capture } label: {
                        Text("Capture Document")
                            .frame(maxWidth: .infinity, minHeight: 46)
                    }
                    .buttonStyle(.bordered)
                }
                .padding(18)
                .background(Color(.systemBackground), in: RoundedRectangle(cornerRadius: 18))

                if let errorMessage {
                    Text(errorMessage)
                        .font(.caption)
                        .foregroundStyle(.red)
                }
            }
            .padding(18)
            .frame(maxWidth: 460)
            .frame(maxWidth: .infinity, alignment: .center)
        }
        .background(Color(.systemGroupedBackground))
    }

    // MARK: — Sign in

    private func signInView(payload: PairingQRCodePayload) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                Text("Sign in to Fichero")
                    .font(.largeTitle.bold())

                VStack(spacing: 14) {
                    TextField("Username", text: $username)
                        .textContentType(.username)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .textFieldStyle(.roundedBorder)
                        .frame(minHeight: 46)

                    SecureField("Password", text: $password)
                        .textContentType(.password)
                        .textFieldStyle(.roundedBorder)
                        .frame(minHeight: 46)

                    Button {
                        Task { await signIn(payload: payload) }
                    } label: {
                        Group {
                            if isPairing {
                                ProgressView()
                            } else {
                                Text("Sign In")
                            }
                        }
                        .frame(maxWidth: .infinity, minHeight: 46)
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(isPairing)
                }
                .padding(18)
                .background(Color(.systemBackground), in: RoundedRectangle(cornerRadius: 18))

                if let errorMessage {
                    Text(errorMessage)
                        .font(.caption)
                        .foregroundStyle(.red)
                }
            }
            .padding(18)
            .frame(maxWidth: 460)
            .frame(maxWidth: .infinity, alignment: .center)
        }
        .background(Color(.systemGroupedBackground))
    }

    // MARK: — Capture

    private var captureView: some View {
        NavigationStack {
            List {
                Section {
                    #if os(visionOS)
                    Button { pickerSource = .library } label: {
                        Label("Choose From Library", systemImage: "photo.on.rectangle")
                            .frame(maxWidth: .infinity, minHeight: 46)
                    }
                    .buttonStyle(.borderedProminent)
                    #else
                    Button { pickerSource = .camera } label: {
                        Label("Capture Document", systemImage: "camera")
                            .frame(maxWidth: .infinity, minHeight: 46)
                    }
                    .buttonStyle(.borderedProminent)
                    #endif

                    if let captureError {
                        Text(captureError)
                            .font(.caption)
                            .foregroundStyle(.red)
                    }
                }

                if !captureQueue.items.isEmpty {
                    Section {
                        ForEach(captureQueue.items) { item in
                            InlineCaptureRow(item: item, queue: captureQueue)
                        }
                        .onDelete { indexSet in
                            for index in indexSet {
                                captureQueue.removeItem(id: captureQueue.items[index].id)
                            }
                        }
                    }
                }
            }
            .navigationTitle("Capture Document")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Back") { phase = .connect }
                }
            }
        }
    }

    // MARK: — Helpers

    private var supportsCameraScanner: Bool {
        #if os(visionOS)
        return false
        #else
        return AVCaptureDevice.default(for: .video) != nil
        #endif
    }

    private func handleScannedMessage(_ message: String) {
        do {
            let payload = try PairingQRCodePayloadDecoder.decode(message: message)
            errorMessage = nil
            phase = .signingIn(payload)
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func signIn(payload: PairingQRCodePayload) async {
        isPairing = true
        errorMessage = nil
        defer { isPairing = false }
        do {
            let inviteText = try RemoteClientPairing.inviteLinkString(from: payload)
            let fields = try RemoteClientPairing.pairingFields(fromInviteOrPayload: inviteText)
            _ = try await RemoteClientPairing.pairAndPersistHost(
                remoteURL: fields.remoteURL,
                pairCode: fields.pairCode,
                deviceName: RemoteClientPairing.defaultDeviceName(),
                expectedSPKIPin: fields.spkiPin
            )
            // ponytail: username/password not validated — wire to /api/auth/login when #2021 ships
            appState.reconfigureGeneratedClientsForCurrentHost()
            libraryManager.reconfigureGeneratedClientsForCurrentHost()
            await onConnected()
            if !appState.isBackendRunning {
                errorMessage = "Paired but the host is not responding yet."
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func handleCapturedImage(_ image: UIImage, source: CaptureSource) {
        pickerSource = nil
        let jpegData = image.jpegData(compressionQuality: 0.9)
        guard let data = jpegData ?? image.pngData() else {
            captureError = "Could not encode the captured image."
            return
        }
        do {
            let catalog = MobileCaptureCatalogFields(sourceArchiveHint: source.defaultSourceHint)
            _ = try captureQueue.enqueueCapturedImage(
                data,
                catalog: catalog,
                fileExtension: jpegData == nil ? "png" : "jpg"
            )
            captureError = nil
        } catch {
            captureError = error.localizedDescription
        }
    }
}

private struct InlineCaptureRow: View {
    let item: MobileCaptureQueueItem
    @ObservedObject var queue: MobileCaptureQueueStore

    var body: some View {
        HStack(spacing: 12) {
            thumbnailView
            Text(item.catalog.documentName(fallback: item.imageFileName))
                .font(.body.weight(.semibold))
                .lineLimit(2)
        }
        .padding(.vertical, 4)
    }

    private var thumbnailView: some View {
        Group {
            if let image = UIImage(contentsOfFile: queue.imageURL(for: item).path) {
                Image(uiImage: image)
                    .resizable()
                    .scaledToFill()
            } else {
                ZStack {
                    Color.accentColor.opacity(0.12)
                    Image(systemName: "photo")
                        .foregroundStyle(Color.accentColor)
                }
            }
        }
        .frame(width: 42, height: 42)
        .clipShape(RoundedRectangle(cornerRadius: 11))
    }
}

private struct QRCodeScannerSheet: View {
    let onCancel: () -> Void
    let onMessage: (String) -> Void

    @State private var errorMessage: String?

    var body: some View {
        NavigationStack {
            VStack(spacing: 16) {
                Text("Open Fichero on the Mac, open Settings, and scan the QR code shown there.")
                    .font(.headline)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal)

                #if os(visionOS)
                VStack(spacing: 12) {
                    Image(systemName: "qrcode.viewfinder")
                        .font(.largeTitle)
                    Text("Camera QR scanning is unavailable on visionOS. Use the manual link section below.")
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
