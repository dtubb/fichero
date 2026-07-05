#if os(iOS) || os(tvOS) || os(visionOS)
import AVFoundation
import FicheroAPIClient
import OSLog
import SwiftUI
import UIKit
#if canImport(VisionKit) && !os(tvOS) && !os(visionOS)
import VisionKit
#endif
// swiftlint:disable file_length

@main
struct FicheroAppIOS: App {
    @State private var backendService = EmbeddedBackendService()
    @State private var appState = AppState()
    @State private var viewSettings = ViewSettings()
    @State private var libraryManager = LibraryManager.shared
    @State private var windowState = WindowState(libraryId: LibraryManager.globalLibraryId)
    @State private var claimFocusState = ClaimFocusState.shared
    @State private var kgFocusState = KGFocusState.shared
    @State private var executionObserver = WorkflowExecutionObserver()
    @State private var captureQueue = MobileCaptureQueueStore()

    var body: some Scene {
        // `id: "main"` so `openWindow(id: "main")` (new-window / new-tab
        // affordances, WindowOpener) targets a registered scene on iPad instead
        // of being a silent no-op (#2815). Harmless on iPhone, which has no
        // multi-window support.
        WindowGroup(id: "main") {
            FicheroSharedPlatformRoot(
                windowState: windowState,
                executionObserver: executionObserver
            )
                .environment(windowState)
                .environment(backendService)
                .environment(appState)
                .environment(viewSettings)
                .environment(libraryManager)
                .environment(claimFocusState)
                .environment(appState.mcpService)
                .environment(captureQueue)
                .environment(kgFocusState)
                // Launch connects via the SAME entry point as the Retry button
                // and pairing (#3108): FicheroSharedPlatformRoot owns the single
                // `reconnectToConfiguredHost()` task.
        }

        // Detached document-detail scene, mirroring the macOS registration so
        // the inspector's "Open in Window" affordance (DetachInspectorButton →
        // openWindow(id: "document-detail")) resolves on iPad instead of being a
        // silent no-op (#2815). iPhone gates the button off (single-window).
        WindowGroup("Document", id: "document-detail") {
            DocumentDetailWindow()
                .environment(libraryManager)
                .environment(claimFocusState)
                .environment(kgFocusState)
        }
    }
}

private struct IdentifiableURL: Identifiable {
    let url: URL
    var id: String { url.absoluteString }
}

private struct FicheroSharedPlatformRoot: View {
    private let logger = Logger(subsystem: "app.fichero.fichero", category: "FicheroSharedPlatformRoot")
    @Environment(AppState.self) private var appState
    @Environment(LibraryManager.self) private var libraryManager
    @Environment(MobileCaptureQueueStore.self) private var captureQueue

    let windowState: WindowState
    let executionObserver: WorkflowExecutionObserver

    @State private var pendingPairURL: IdentifiableURL?

    private var activeLibrary: LibraryManager.LibraryReference? {
        LibraryWorkspaceSelection.activeLibrary(
            currentLibraryId: libraryManager.currentLibraryId,
            windowLibraryId: windowState.libraryId,
            libraryManager: libraryManager
        )
    }

    var body: some View {
        // The SAME root gate as macOS, switching on the single phase (#3107):
        // setupNeeded → pairing; ready → workspace; every other phase →
        // BackendConnectionView (splash/diagnosis + Retry). No blank screen, and
        // a configured-but-unreachable host shows the error, never the pairing
        // prompt (#2864). backendService flows in via @EnvironmentObject.
        BackendRootGate(
            appState: appState,
            onRetry: { await reconnectToConfiguredHost() },
            setup: {
                RemoteConnectionSetupView {
                    await reconnectToConfiguredHost()
                }
            },
            content: {
                if let library = activeLibrary {
                    LibraryWorkspaceRoot(
                        library: library,
                        windowState: windowState,
                        executionObserver: executionObserver
                    )
                        .environment(windowState)
                        .environment(library.apiClient)
                } else {
                    ContentUnavailableView(
                        "Library Unavailable",
                        systemImage: "externaldrive.badge.exclamationmark",
                        description: Text("Fichero could not load the Local library.")
                    )
                }
            }
        )
        .onOpenURL { url in
            guard url.scheme?.lowercased() == "fichero", url.host?.lowercased() == "pair" else { return }
            pendingPairURL = IdentifiableURL(url: url)
        }
        .sheet(item: $pendingPairURL) { wrapper in
            PairingIncomingLinkSheet(url: wrapper.url) {
                await reconnectToConfiguredHost()
            }
            .environment(appState)
            .environment(libraryManager)
            .environment(captureQueue)
        }
        // Launch connects through the SAME entry point as the Retry button and
        // pairing (#3108) — one iOS connect path, no divergent launch task.
        .task { await reconnectToConfiguredHost() }
    }

    /// The ONE iOS connect entry point (#3108): launch, the connection view's
    /// Retry, and incoming-pair all call this. Pairing is checked FIRST so a
    /// fresh, unpaired install shows first-run setup instead of a pointless
    /// probe-then-unreachable flash.
    private func reconnectToConfiguredHost() async {
        // Pure phase decision (#3113): with no paired library the launch is
        // `setupNeeded` regardless of reachability — a fresh install shows
        // first-run pairing instead of probing localhost (#2465). Reachability
        // is unknown until the probe, so `isReachable: false` here only gates
        // the setupNeeded branch; the probe below resolves ready vs unreachable.
        guard EngineConfig.iosLaunchPhase(
            hasPairedLibrary: RemoteAccessConfig.hasPairedLibraryPath,
            isReachable: false
        ) != .setupNeeded else {
            appState.engine.markSetupNeeded()
            return
        }
        // checkBackendHealth resolves the phase to ready / unreachable /
        // authRejected. A configured-but-down host lands on `unreachable` and
        // the gate shows the diagnosis — NEVER the pairing prompt (#2807/#2864).
        await appState.checkBackendHealth()
        guard appState.isBackendRunning else {
            logger.error(
                "External backend is not reachable at \(EngineConfig.host.absoluteString, privacy: .public)"
            )
            return
        }
        appState.startBackendHeartbeat()
        // Proactively renew the device token if it is near expiry (#3096), before
        // it can lapse into a 401. No-op for local hosts / unknown expiry; a failed
        // renew keeps the old token (the expired → re-pair path is the safety net).
        await DeviceTokenRenewal.renewIfNeeded(host: EngineConfig.host)
        // The SAME shared post-ready block as macOS (#3113), then the iOS-only
        // capture-queue resume — which is a mobile concern, not a library one.
        await libraryManager.refreshAfterBackendBecameReady()
        _ = await captureQueue.resumePendingUploads(
            using: MobileCaptureBackendUploadClient(libraryManager: libraryManager)
        )
    }
}

private struct PairingIncomingLinkSheet: View {
    @Environment(AppState.self) private var appState
    @Environment(LibraryManager.self) private var libraryManager
    @Environment(MobileCaptureQueueStore.self) private var captureQueue
    @Environment(\.dismiss) private var dismiss

    let url: URL
    let onConnected: @MainActor () async -> Void

    @State private var isPairing = true
    @State private var errorMessage: String?

    var body: some View {
        NavigationStack {
            Group {
                if isPairing {
                    ProgressView("Connecting…")
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else if let errorMessage {
                    VStack(spacing: 16) {
                        Image(systemName: "exclamationmark.triangle")
                            .font(.largeTitle)
                            .foregroundStyle(.red)
                        Text(errorMessage)
                            .multilineTextAlignment(.center)
                            .padding(.horizontal)
                    }
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                }
            }
            .navigationTitle("Connecting…")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
            }
        }
        .task { await pair() }
    }

    private func pair() async {
        isPairing = true
        errorMessage = nil
        do {
            let fields = try RemoteClientPairing.pairingFields(fromInviteOrPayload: url.absoluteString)
            _ = try await RemoteClientPairing.pairAndPersistHost(
                remoteURL: fields.remoteURL,
                pairCode: fields.pairCode,
                deviceName: RemoteClientPairing.defaultDeviceName(),
                expectedSPKIPin: fields.spkiPin,
                libraryPath: fields.libraryPath
            )
            // Pairing persisted the new host; repoint the app-level client so
            // the reconnect probe targets it. Library adoption + reload fire once
            // in the ready transition (`onConnected` → refreshAfterBackendBecameReady,
            // #3113) — no duplicate adopt here.
            appState.reconfigureGeneratedClientsForCurrentHost()
            dismiss()
            await onConnected()
        } catch {
            isPairing = false
            errorMessage = error.localizedDescription
        }
    }
}

private struct RemoteConnectionSetupView: View {
    @Environment(AppState.self) private var appState
    @Environment(LibraryManager.self) private var libraryManager
    @Environment(MobileCaptureQueueStore.self) private var captureQueue

    let onConnected: @MainActor () async -> Void

    // Companion-first onboarding (#3102): lead with Macs discovered on the LAN so
    // the primary path is pairing to an existing engine, not standing up a local
    // library. Discovery only *finds* the Mac — the QR still carries the pair code
    // + SPKI pin, so tapping a host routes into the scanner.
    @StateObject private var discovery = BonjourDiscoveryService()
    @State private var showingScanner = false
    @State private var didAutoPresentScanner = false
    @State private var showingManualEntry = false
    @State private var isPairing = false
    @State private var errorMessage: String?
    @State private var pickerSource: CaptureSource?
    @State private var showingDocumentScanner = false
    @State private var captureError: String?

    var body: some View {
        connectView
        // #2347: on iPhone/iPad the pairing screen opens STRAIGHT into QR
        // scanning — the whole point is to scan the host Mac's code. Present the
        // scanner once on first appearance; after a Cancel the landing card's
        // "Scan QR Code" button (and manual paths) remain as the fallback, so the
        // user is never trapped in a re-presenting camera. Camera-less platforms
        // (visionOS/tvOS) skip this and just show the card.
        .onAppear {
            guard !didAutoPresentScanner, supportsCameraScanner, !isPairing else { return }
            didAutoPresentScanner = true
            showingScanner = true
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
        .sheet(isPresented: $showingManualEntry) {
            ManualPairingEntrySheet(
                isPairing: isPairing,
                onCancel: { showingManualEntry = false },
                onConnect: handleManualInvite
            )
        }
        #if !os(tvOS)
        .sheet(item: $pickerSource) { source in
            MobileCaptureImagePicker(
                sourceType: source.sourceType,
                onImage: { image in handleCapturedImage(image, source: source) },
                onCancel: { pickerSource = nil }
            )
        }
        #endif
        #if canImport(VisionKit) && !os(tvOS) && !os(visionOS)
        .fullScreenCover(isPresented: $showingDocumentScanner) {
            MobileDocumentScanner(
                onImages: handleScannedDocumentImages,
                onCancel: { showingDocumentScanner = false }
            )
        }
        #endif
    }

    // MARK: — Connect

    private var connectView: some View {
        NavigationStack {
            List {
                DiscoveredMacsSection(
                    discovery: discovery,
                    isPairing: isPairing,
                    onSelectHost: {
                        if supportsCameraScanner {
                            showingScanner = true
                        } else {
                            errorMessage = "Camera scanning is unavailable on this device."
                        }
                    }
                )

                Section {
                    ZStack {
                        RoundedRectangle(cornerRadius: 22)
                            .fill(Color.accentColor.opacity(0.08))
                            .overlay(
                                RoundedRectangle(cornerRadius: 22)
                                    .stroke(Color.accentColor.opacity(0.18), lineWidth: 1)
                            )
                        if isPairing {
                            ProgressView("Connecting…")
                        } else {
                            VStack(spacing: 14) {
                                Image("Engine")
                                    .resizable()
                                    .interpolation(.high)
                                    .scaledToFit()
                                    .frame(width: 112, height: 112)
                                    .accessibilityHidden(true)

                                Image(systemName: "qrcode.viewfinder")
                                    .font(.system(size: 34))
                                    .foregroundStyle(Color.accentColor)
                                    .accessibilityHidden(true)
                            }
                        }
                    }
                    .frame(height: 220)
                    .listRowInsets(EdgeInsets(top: 18, leading: 18, bottom: 14, trailing: 18))

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
                    .disabled(isPairing)

                    // Fallback/debug pairing (#2350): paste an invite link or QR
                    // text. Primary path on visionOS (camera scanning unavailable)
                    // and a rescue on iPhone/iPad when the camera can't be used.
                    Button {
                        showingManualEntry = true
                    } label: {
                        Label("Enter Link Manually", systemImage: "link")
                            .frame(maxWidth: .infinity, minHeight: 46)
                    }
                    .buttonStyle(.bordered)
                    .disabled(isPairing)

                    #if os(tvOS)
                    Text("Capture is unavailable on Apple TV.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    #elseif os(visionOS)
                    Button { pickerSource = .library } label: {
                        Label("Capture Document", systemImage: "photo.on.rectangle")
                            .frame(maxWidth: .infinity, minHeight: 46)
                    }
                    .buttonStyle(.bordered)
                    .disabled(isPairing)
                    #else
                    Button {
                        if supportsDocumentScanner {
                            showingDocumentScanner = true
                        } else {
                            pickerSource = .camera
                        }
                    } label: {
                        Label("Capture Document", systemImage: "doc.viewfinder")
                            .frame(maxWidth: .infinity, minHeight: 46)
                    }
                    .buttonStyle(.bordered)
                    .disabled(isPairing)
                    #endif

                    if let errorMessage {
                        Text(errorMessage)
                            .font(.caption)
                            .foregroundStyle(.red)
                    }
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
            .navigationTitle("Connect to Fichero on Mac")
            .onAppear { discovery.start() }
        }
    }

    // MARK: — Helpers

    private var supportsCameraScanner: Bool {
        #if os(tvOS) || os(visionOS)
        return false
        #else
        return AVCaptureDevice.default(for: .video) != nil
        #endif
    }

    private var supportsDocumentScanner: Bool {
        #if canImport(VisionKit) && !os(tvOS) && !os(visionOS)
        return VNDocumentCameraViewController.isSupported
        #else
        return false
        #endif
    }

    private func handleScannedMessage(_ message: String) {
        do {
            let payload = try PairingQRCodePayloadDecoder.decode(message: message)
            errorMessage = nil
            Task { await pair(with: payload) }
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func pair(with payload: PairingQRCodePayload) async {
        do {
            try await finishPairing(with: RemoteClientPairing.pairingFields(from: payload))
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

    private func handleScannedDocumentImages(_ images: [UIImage]) {
        #if canImport(VisionKit) && !os(tvOS) && !os(visionOS)
        showingDocumentScanner = false
        #endif
        for image in images {
            let jpegData = image.jpegData(compressionQuality: 0.9)
            guard let data = jpegData ?? image.pngData() else {
                captureError = "Could not encode the scanned page."
                return
            }

            do {
                let catalog = MobileCaptureCatalogFields(sourceArchiveHint: "document-camera")
                _ = try captureQueue.enqueueCapturedImage(
                    data,
                    catalog: catalog,
                    fileExtension: jpegData == nil ? "png" : "jpg"
                )
                captureError = nil
            } catch {
                captureError = error.localizedDescription
                return
            }
        }
    }
}

private extension RemoteConnectionSetupView {
    /// Manual fallback/debug path (#2350): pair from a pasted invite link or raw
    /// QR payload text. This is the ONLY pairing route on visionOS (no camera
    /// scanner) and the fallback on iPhone/iPad when the camera is unavailable.
    func handleManualInvite(_ text: String) {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        showingManualEntry = false
        Task {
            do {
                try await finishPairing(with: RemoteClientPairing.pairingFields(fromInviteOrPayload: trimmed))
            } catch {
                errorMessage = error.localizedDescription
            }
        }
    }

    func finishPairing(with fields: RemoteClientPairingFields) async throws {
        isPairing = true
        errorMessage = nil
        defer { isPairing = false }
        _ = try await RemoteClientPairing.pairAndPersistHost(
            remoteURL: fields.remoteURL,
            pairCode: fields.pairCode,
            deviceName: RemoteClientPairing.defaultDeviceName(),
            expectedSPKIPin: fields.spkiPin,
            libraryPath: fields.libraryPath
        )
        // Repoint the app-level client at the freshly-paired host; adopt +
        // reload fire once in the ready transition (#3113), not here.
        appState.reconfigureGeneratedClientsForCurrentHost()
        await onConnected()
        if !appState.isBackendRunning {
            errorMessage = "Connected — Fichero on your Mac is not responding yet."
        }
    }
}

/// Discovered-Mac list that leads first-run onboarding (#3102). Discovery only
/// surfaces *which* Mac is on the LAN; selecting one opens the QR scanner because
/// pairing needs the code + SPKI pin shown on that Mac — the scan grants trust.
private struct DiscoveredMacsSection: View {
    @ObservedObject var discovery: BonjourDiscoveryService
    let isPairing: Bool
    let onSelectHost: () -> Void

    var body: some View {
        Section {
            if discovery.hosts.isEmpty {
                HStack(spacing: 10) {
                    ProgressView().controlSize(.small)
                    Text("Searching for Fichero on your network…")
                        .foregroundStyle(.secondary)
                }
            } else {
                ForEach(discovery.hosts) { host in
                    Button(action: onSelectHost) {
                        Label {
                            VStack(alignment: .leading, spacing: 2) {
                                Text(host.displayName)
                                Text(host.hasReachableURL
                                    ? "On your network — scan its QR code to pair"
                                    : "Found — scan its QR code to pair")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        } icon: {
                            Image(systemName: "desktopcomputer")
                                .foregroundStyle(Color.accentColor)
                        }
                    }
                    .disabled(isPairing)
                }
            }
        } header: {
            Text("Connect to your Mac")
        }
    }
}

private struct InlineCaptureRow: View {
    let item: MobileCaptureQueueItem
    @Bindable var queue: MobileCaptureQueueStore

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

/// Manual fallback/debug pairing entry (#2350): accepts an invite link
/// (`fichero://pair?…`) or raw QR payload text. Reuses the same
/// `RemoteClientPairing.pairingFields(fromInviteOrPayload:)` path the scanner
/// funnels into, so validation (HTTPS/SPKI) is identical — this is entry only,
/// never a bypass. Primary route on visionOS (no camera scanner).
private struct ManualPairingEntrySheet: View {
    let isPairing: Bool
    let onCancel: () -> Void
    let onConnect: (String) -> Void

    @State private var invite = ""

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField("Invite link or QR text", text: $invite, axis: .vertical)
                        .lineLimit(3...6)
                        .autocorrectionDisabled()
                        .textInputAutocapitalization(.never)
                } header: {
                    Text("Paste the invite link or QR text from the host Mac.")
                } footer: {
                    Text("Use this only if the camera is unavailable. The link is validated the same way as a scanned code.")
                }

                Section {
                    #if !os(tvOS)
                    Button {
                        if let pasted = UIPasteboard.general.string {
                            invite = pasted
                        }
                    } label: {
                        Label("Paste from Clipboard", systemImage: "doc.on.clipboard")
                    }
                    .disabled(isPairing)
                    #endif

                    Button {
                        onConnect(invite)
                    } label: {
                        Label(isPairing ? "Connecting…" : "Connect", systemImage: "link")
                    }
                    .disabled(isPairing || invite.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                }
            }
            .navigationTitle("Enter Link Manually")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel", action: onCancel)
                }
            }
        }
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

                #if os(tvOS)
                VStack(spacing: 12) {
                    Image(systemName: "qrcode.viewfinder")
                        .font(.largeTitle)
                    Text("Camera QR scanning is unavailable on Apple TV. Use another Fichero device to scan the code.")
                        .multilineTextAlignment(.center)
                        .foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity, minHeight: 320)
                .padding()
                .background(Color.secondary.opacity(0.08), in: RoundedRectangle(cornerRadius: 20))
                #elseif os(visionOS)
                VStack(spacing: 12) {
                    Image(systemName: "qrcode.viewfinder")
                        .font(.largeTitle)
                    Text("Camera QR scanning is unavailable on visionOS. Use another Fichero device to scan the code.")
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

#if !os(tvOS) && !os(visionOS)
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
        hosts = records.values.sorted {
            $0.displayName.localizedCaseInsensitiveCompare($1.displayName) == .orderedAscending
        }
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
