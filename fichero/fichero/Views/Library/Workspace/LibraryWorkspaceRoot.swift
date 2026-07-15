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
            .environment(windowState)
            .environment(library.savedSearchServiceGenerated)
            .environment(library.bookmarkServiceGenerated)
            .environment(library.searchService)
            .environment(library.conversationServiceGenerated)
            .environment(library.chatServiceGenerated)
            .environment(library.workspaceStore)
            .environment(library.batchStore)
            .environment(library.workflowStore)
            .environment(library.workflowServiceGenerated)
            .environment(library.workflowStreamService)
            .environment(library.importService)
            .environment(library.documentServiceGenerated)
            .environment(library.storageService)
            .environment(library.providerService)
            .environment(library.modelService)
            .environment(library.artifactService)
            .environment(library.entityService)
            .environment(library.kgCurationService)
            .environment(library.researchService)
            .environment(executionObserver)
            .environment(library.entityStore)
            .environment(library.claimStore)
            .environment(library.noteStore)
            .environment(library.annotationStore)
            .environment(library.actionStore)
            .environment(library.activityStore)
            .environment(library.chainStore)
            .environment(library.workflowExecutionStore)
            .environment(library.auditStore)
            .environment(library.researchStore)
            .environment(library.searchStore)
            .environment(library.artifactStore)
            .environment(library.citationStore)
            .environment(library.referenceStore)
            .environment(library.interpretationStore)
            .environment(library.changeStream)
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
