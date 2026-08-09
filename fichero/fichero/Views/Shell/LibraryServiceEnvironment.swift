import SwiftUI

// ONE list of a library's service/store environment (2026-08-08).
//
// Why: SwiftUI hosts some presentation contexts OUTSIDE the tab tree that
// carries the library environment — `.inspector` content, detached windows,
// preview hosts. Each such boundary needs the full re-injection, and the two
// existing copies (LibraryWorkspaceRoot's tree injection and
// FocusedDocument's detached-inspector list) had already drifted from each
// other. Tonight's live crash loop was the third copy NOT existing: the
// DOCKED inspector content had no re-injection at all, so the moment a
// restored `detailDocument` mounted DocumentInspector at launch it died on
// the first `@Environment(ArtifactService.self)` read — a process-killing
// assertion, relaunched into the same restored state, crashed again.
//
// Add new library services HERE and every boundary gets them.

extension View {
    /// Re-inject the FULL library service environment across a hosting
    /// boundary. `library` is the window's current library reference.
    func libraryServiceEnvironment(_ library: LibraryManager.LibraryReference) -> some View {
        self
            .environment(library.savedSearchService)
            .environment(library.bookmarkService)
            .environment(library.searchService)
            .environment(library.conversationService)
            .environment(library.chatService)
            .environment(library.workspaceStore)
            .environment(library.batchStore)
            .environment(library.workflowStore)
            .environment(library.workflowService)
            .environment(library.workflowStreamService)
            .environment(library.importService)
            .environment(library.documentService)
            .environment(library.storageService)
            .environment(library.providerService)
            .environment(library.modelService)
            .environment(library.artifactService)
            .environment(library.entityService)
            .environment(library.kgCurationService)
            .environment(library.researchService)
            .environment(library.apiClient)
            .environment(library.documentStore)
            .environment(library.entityStore)
            .environment(library.claimStore)
            .environment(library.noteStore)
            .environment(library.annotationStore)
            .environment(library.actionStore)
            // The docked inspector hosts the WHOLE detail view
            // (`inspectorContainerView` → `detailView`), so Activity and the
            // chain surfaces mount across this boundary too. All three were
            // missing here while `check_environment_forwarding` reported zero
            // gaps — it only looked at DocumentTabView. `ActivityBrowserView`
            // reads ActivityStore non-optionally: the next crash, already
            // loaded.
            .environment(library.activityStore)
            .environment(library.chainStore)
            .environment(library.workflowExecutionStore)
            .environment(library.auditStore)
            .environment(library.researchStore)
            .environment(library.searchStore)
            .environment(library.artifactStore)
            .environment(library.citationStore)
            .environment(library.referenceStore)
            // Found by the 2026-08-08 night review BEFORE the crash: these two
            // are in FocusedDocument's list but were missing here —
            // DocumentInterpretationsSection reads InterpretationStore
            // non-optionally from the docked inspector.
            .environment(library.interpretationStore)
            .environment(library.changeStream)
    }
}
