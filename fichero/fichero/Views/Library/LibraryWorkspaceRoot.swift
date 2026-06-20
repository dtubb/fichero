import SwiftUI

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
    @EnvironmentObject private var libraryManager: LibraryManager
    #if canImport(UIKit) && !os(macOS)
    @EnvironmentObject private var captureQueue: MobileCaptureQueueStore
    @State private var showingCaptureQueue = false
    #endif

    let library: LibraryManager.LibraryReference
    let windowState: WindowState
    let executionObserver: WorkflowExecutionObserver

    var body: some View {
        DocumentTabView(
            libraryId: library.id,
            document: Binding(
                get: { library.document },
                set: { library.document = $0 }
            ),
            documentURL: LibraryWorkspaceSelection.documentURL(for: library.url, libraryManager: libraryManager)
        )
        .environmentObject(windowState)
        .environment(library.documentStore)
        .environmentObject(library.savedSearchServiceGenerated)
        .environmentObject(library.searchService)
        .environmentObject(library.conversationServiceGenerated)
        .environmentObject(library.chatServiceGenerated)
        .environment(library.workflowStore)
        .environmentObject(library.workflowServiceGenerated)
        .environmentObject(library.workflowStreamService)
        .environmentObject(library.importService)
        .environmentObject(library.documentServiceGenerated)
        .environmentObject(library.storageService)
        .environmentObject(library.providerService)
        .environmentObject(library.modelService)
        .environmentObject(library.artifactService)
        .environmentObject(library.entityService)
        .environmentObject(library.kgCurationService)
        .environmentObject(library.researchService)
        .environment(executionObserver)
        .environment(library.entityStore)
        .environment(library.claimStore)
        .environment(library.noteStore)
        .environment(library.annotationStore)
        .environment(library.actionStore)
        .environment(library.auditStore)
        .environment(library.researchStore)
        .environment(library.searchStore)
        .environment(library.artifactStore)
        .environment(library.citationStore)
        .environment(library.referenceStore)
        .environment(library.interpretationStore)
        .environment(library.changeStream)
        .task(id: library.id) {
            if windowState.libraryId != library.id {
                windowState.libraryId = library.id
            }
            library.changeStream.start()
        }
        #if canImport(UIKit) && !os(macOS)
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button {
                    showingCaptureQueue = true
                } label: {
                    Label(captureQueue.pendingCount > 0 ? "Queue \(captureQueue.pendingCount)" : "Capture Queue", systemImage: "camera")
                }
                .help("Open the mobile capture queue")
            }
        }
        .sheet(isPresented: $showingCaptureQueue) {
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
        #endif
    }
}
