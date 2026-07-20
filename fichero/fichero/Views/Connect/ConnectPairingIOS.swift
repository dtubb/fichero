#if os(iOS) || os(tvOS) || os(visionOS)
import AVFoundation
import SwiftUI
import UIKit
#if canImport(VisionKit) && !os(tvOS) && !os(visionOS)
import VisionKit
#endif

// Promoted private → internal: presented by `FicheroSharedPlatformRoot`
// (FicheroApp_iOS.swift) after this type was split out for file_length.
struct PairingIncomingLinkSheet: View {
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

// Promoted private → internal: presented by `FicheroSharedPlatformRoot`
// (FicheroApp_iOS.swift) as the `setup:` view of `BackendRootGate`, after this
// type was split out for file_length.
struct RemoteConnectionSetupView: View {
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

#endif
