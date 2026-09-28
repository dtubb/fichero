import SwiftUI
#if canImport(UIKit) && !os(macOS)
import UIKit
#if canImport(VisionKit) && !os(visionOS)
import VisionKit
#endif
#endif

enum LibraryWorkspaceSelection {
    @MainActor
    static func activeLibrary(
        currentLibraryId: UUID?,
        windowLibraryId: UUID,
        libraryManager: LibraryManager
    ) -> LibraryManager.LibraryReference? {
        if let currentLibraryId,
           let library = libraryManager.getLibrary(id: currentLibraryId) {
            return library
        }

        if let library = libraryManager.getLibrary(id: windowLibraryId) {
            return library
        }

        return libraryManager.globalLibrary
    }

    @MainActor
    static func documentURL(for libraryURL: URL, libraryManager: LibraryManager) -> URL? {
        libraryManager.isTemporaryLibrary(libraryURL) ? nil : libraryURL
    }
}

/// Shared library/document host used by every Fichero app entry surface.
/// macOS wraps it in `LibraryWindow` for window chrome and commands; iPhone,
/// iPad, and visionOS embed the same workspace directly.
struct LibraryWorkspaceRoot: View {
    @Environment(AppState.self) private var appState
    @Environment(FeatureManager.self) private var featureManager
    @Environment(LibraryManager.self) private var libraryManager
    #if canImport(UIKit) && !os(macOS)
    @Environment(MobileCaptureQueueStore.self) private var captureQueue
    @State private var showingCaptureQueue = false
    @State private var capturePickerSource: CaptureSource?
    #if canImport(VisionKit) && !os(visionOS)
    @State private var showingDirectDocumentScanner = false
    #endif
    #endif

    let library: LibraryManager.LibraryReference
    let windowState: WindowState
    let executionObserver: WorkflowExecutionObserver

    var body: some View {
        AdaptiveAppleShellHost {
            DocumentTabView(
                libraryId: library.id,
                document: Binding(
                    get: { library.document },
                    set: { library.document = $0 }
                ),
                documentURL: LibraryWorkspaceSelection.documentURL(for: library.url, libraryManager: libraryManager)
            )
            // These reach every view in THIS tree by inheritance — that is
            // how SwiftUI's environment works, and no descendant needs them
            // forwarded again (#4455). Measured: 14 of these types are read
            // only in-tree, 39 readers between them, none ever crashed while
            // a downstream host omitted them.
            //
            // They do NOT reach content hosted OUTSIDE this tree: toolbar
            // content, which the window lays out, and separate Scenes. A store
            // read by a toolbar item must be injected for the toolbar — that
            // omission is #4448, and it is the only boundary that has ever
            // actually bitten here.
            .modifier(LibraryTreeEnvironment(library: library, windowState: windowState, executionObserver: executionObserver))
            .task(id: "\(library.id.uuidString)-\(appState.isBackendRunning)") {
                if windowState.libraryId != library.id {
                    windowState.libraryId = library.id
                }
                // Don’t start the live-update streams until the backend has
                // completed its readiness handshake. Starting them while the
                // app is still probing the engine can falsely trip the paused
                // pill until the user taps Reconnect (#3351).
                guard appState.isBackendRunning else { return }
                library.changeStream.start()
                if featureManager.isVisible(.activity) {
                    library.activityStore.start()
                }
                // The engine's bundled fonts, for text the system cannot draw (MUFI, #5210): once per app.
                await BundledFonts.shared.load(from: library.ficheroClient)
            }
        }
        .environment(library.documentStore)
        #if canImport(UIKit) && !os(macOS)
        .toolbar {
            // Library switcher (#2394) — the registry of libraries the paired Mac
            // has, surfaced first so a phone can open more than the default library.
            // `.topBarLeading` is unavailable on tvOS, so guard it there.
            #if !os(tvOS)
            ToolbarItem(placement: .topBarLeading) {
                IOSLibraryPickerMenu()
            }
            #endif
            ToolbarItem(placement: .primaryAction) {
                Menu {
                    #if os(tvOS)
                    Text("Capture is unavailable on Apple TV.")
                    #elseif os(visionOS)
                    Button { capturePickerSource = .library } label: {
                        Label("Choose from Library", systemImage: "photo.on.rectangle")
                    }
                    #else
                    Button {
                        if supportsDocumentScanner {
                            showingDirectDocumentScanner = true
                        } else {
                            capturePickerSource = .camera
                        }
                    } label: {
                        Label("Scan Document", systemImage: "doc.viewfinder")
                    }
                    Button { capturePickerSource = .library } label: {
                        Label("Choose from Library", systemImage: "photo.on.rectangle")
                    }
                    #endif
                    Divider()
                    Button { showingCaptureQueue = true } label: {
                        let label = captureQueue.pendingCount > 0
                            ? "Queue (\(captureQueue.pendingCount))"
                            : "Capture Queue"
                        Label(label, systemImage: "tray.and.arrow.up")
                    }
                } label: {
                    Label("Capture", systemImage: "camera")
                }
                .help("Capture or import a document into this library")
            }
        }
        .sheet(isPresented: $showingCaptureQueue) {
            MobileCaptureQueueView(
                queue: captureQueue,
                retryPendingUploads: {
                    await captureQueue.resumePendingUploads(
                        using: MobileCaptureBackendUploadClient(
                            libraryManager: libraryManager,
                            targetLibraryId: library.id
                        ),
                        retryInterruptedUploads: true
                    )
                }
            )
        }
        #if !os(tvOS)
        .sheet(item: $capturePickerSource) { source in
            MobileCaptureImagePicker(
                sourceType: source.sourceType,
                onImage: { image in handleCapturedImage(image, source: source) },
                onCancel: { capturePickerSource = nil }
            )
        }
        #endif
        #if canImport(VisionKit) && !os(visionOS)
        .fullScreenCover(isPresented: $showingDirectDocumentScanner) {
            MobileDocumentScanner(
                onImages: handleScannedDocumentImages,
                onCancel: { showingDirectDocumentScanner = false }
            )
        }
        #endif
        #endif
    }

    // MARK: — Capture helpers (iOS/iPadOS only)

    #if canImport(UIKit) && !os(macOS)
    private var supportsDocumentScanner: Bool {
        #if canImport(VisionKit) && !os(visionOS)
        return VNDocumentCameraViewController.isSupported
        #else
        return false
        #endif
    }

    private func handleCapturedImage(_ image: UIImage, source: CaptureSource) {
        capturePickerSource = nil
        let imageData = image.jpegData(compressionQuality: 0.9)
        let fallbackData = imageData ?? image.pngData()
        guard let data = fallbackData else { return }
        let catalog = MobileCaptureCatalogFields(sourceArchiveHint: source.defaultSourceHint)
        guard (try? captureQueue.enqueueCapturedImage(
            data,
            catalog: catalog,
            fileExtension: imageData == nil ? "png" : "jpg"
        )) != nil else { return }
        startUploadToActiveLibrary()
    }

    private func handleScannedDocumentImages(_ images: [UIImage]) {
        #if canImport(VisionKit) && !os(visionOS)
        showingDirectDocumentScanner = false
        #endif
        let catalog = MobileCaptureCatalogFields(sourceArchiveHint: "document-camera")
        for image in images {
            let imageData = image.jpegData(compressionQuality: 0.9)
            guard let data = imageData ?? image.pngData() else { continue }
            _ = try? captureQueue.enqueueCapturedImage(
                data,
                catalog: catalog,
                fileExtension: imageData == nil ? "png" : "jpg"
            )
        }
        startUploadToActiveLibrary()
    }

    private func startUploadToActiveLibrary() {
        let client = MobileCaptureBackendUploadClient(
            libraryManager: libraryManager,
            targetLibraryId: library.id
        )
        Task {
            await captureQueue.resumePendingUploads(using: client)
        }
    }
    #endif
}

/// What every view in a library window's tree inherits: the window, the ONE library service list
/// (`libraryServiceEnvironment`, never a hand-copied subset) and the execution observer. This tree's own
/// copy had drifted -- no ReadingOrderService, SegmentService, RenditionService or APIClient -- so the
/// Segments pane, hosted here, never got its order service and spun forever (2026-09-28, Daniel's
/// morning build). A modifier so the test hosts a view in exactly this environment.
struct LibraryTreeEnvironment: ViewModifier {
    let library: LibraryManager.LibraryReference
    let windowState: WindowState
    let executionObserver: WorkflowExecutionObserver

    func body(content: Content) -> some View {
        content
            .environment(windowState)
            .libraryServiceEnvironment(library)
            .environment(executionObserver)
    }
}
