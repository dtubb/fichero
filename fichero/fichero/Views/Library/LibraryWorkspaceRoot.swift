import SwiftUI

/// Shared library/document host used by every Fichero app entry surface.
/// macOS wraps it in `LibraryWindow` for window chrome and commands; iPhone,
/// iPad, and visionOS embed the same workspace directly.
struct LibraryWorkspaceRoot: View {
    @EnvironmentObject private var windowState: WindowState
    @EnvironmentObject private var libraryManager: LibraryManager

    let library: LibraryManager.LibraryReference
    let executionObserver: WorkflowExecutionObserver

    var body: some View {
        DocumentTabView(
            libraryId: library.id,
            document: Binding(
                get: { library.document },
                set: { library.document = $0 }
            ),
            documentURL: libraryManager.isTemporaryLibrary(library.url) ? nil : library.url
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
    }
}
