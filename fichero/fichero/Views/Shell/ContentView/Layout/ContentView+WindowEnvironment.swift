import SwiftUI

// MARK: - The ONE window-environment list (2026-09-17)

/// Re-injects every window/app object where a subtree may not inherit them.
///
/// CORRECTION (2026-09-17, second review): this file was first written claiming
/// an applied pane is a "hosting boundary" where SwiftUI starts a fresh
/// environment root. That is FALSE. `AnyView` does not re-root the environment,
/// and there is no `NSHostingView`/`NSHostingController` in app code; every
/// `NSViewRepresentable` we have wraps an AppKit view rather than hosting
/// SwiftUI children. The proof is in the app itself: pane surfaces read
/// `AnnotationStore`, `DocumentService`, `NoteStore` and `ActionStore`
/// NON-optionally, this modifier carries none of them, and they do not trap —
/// which they would if a pane were a fresh root.
///
/// So applying this at the pane/navigation sites is a NO-OP kept for safety, not
/// the fix for anything. The `WorkflowExecutionObserver` crash was NOT a pane
/// boundary: it was a surface mounted OUTSIDE `LibraryWorkspaceRoot` (the
/// LibraryWindow-level sheets/alerts and the no-library prompt), and the
/// app-level fallback observer in `FicheroApp.libraryWindowRoot` is what
/// actually stopped it. Verified by build sequence: with this modifier alone the
/// app still died on the fatal error; with the fallback added it survived.
///
/// Why this is one type instead of a list at each boundary: there were THREE
/// boundaries with three DIFFERENT hand-picked lists (7, 11 and 13 objects),
/// and two of them carried a comment claiming they injected "ALL of them" and
/// "the same set" as the others. Neither was true, and none carried
/// `WorkflowStore` — so mounting a workflow pane trapped in
/// `EnvironmentValues.subscript.getter` with EXC_BREAKPOINT and no app frame in
/// the stack to name the view (Daniel, 2026-09-17). A hand-maintained list at a
/// boundary drifts behind what the panes below it read; the only fix that holds
/// is having one list.
///
/// Re-injecting an object already in scope is a no-op, so this is only ever
/// too-inclusive, never wrong. When `ContentView` gains an object, add it here.
struct WindowEnvironmentModifier: ViewModifier {
    let apiClient: APIClient
    let appState: AppState
    let artifactService: ArtifactService
    let artifactStore: ArtifactStore
    let claimFocusState: ClaimFocusState
    let claimStore: ClaimStore
    let conversationService: ConversationService
    let documentStore: DocumentStore
    let entityService: EntityService
    let entityStore: EntityStore
    let errorService: ErrorService
    let executionObserver: WorkflowExecutionObserver
    let featureManager: FeatureManager
    let importService: ImportService
    let kgCurationService: KGCurationService
    let kgFocusState: KGFocusState
    let libraryManager: LibraryManager
    // OPTIONAL by design (house rule: a reader surface degrades rather than traps).
    // SwiftUI's `.environment(_: T?)` overload passes it through untouched.
    let renditionService: RenditionService?
    let researchService: ResearchService
    let savedSearchService: SavedSearchService
    let storageService: StorageService
    let viewSettings: ViewSettings
    let windowState: WindowState
    let workflowStore: WorkflowStore
    let workflowStreamService: WorkflowStreamService

    func body(content: Content) -> some View {
        content
            .environment(apiClient)
            .environment(appState)
            .environment(artifactService)
            .environment(artifactStore)
            .environment(claimFocusState)
            .environment(claimStore)
            .environment(conversationService)
            .environment(documentStore)
            .environment(entityService)
            .environment(entityStore)
            .environment(errorService)
            .environment(executionObserver)
            .environment(featureManager)
            .environment(importService)
            .environment(kgCurationService)
            .environment(kgFocusState)
            .environment(libraryManager)
            .environment(renditionService)
            .environment(researchService)
            .environment(savedSearchService)
            .environment(storageService)
            .environment(viewSettings)
            .environment(windowState)
            .environment(workflowStore)
            .environment(workflowStreamService)
    }
}

extension ContentView {
    /// The window's object set, ready to apply at a hosting boundary:
    /// `.modifier(windowEnvironment)`.
    var windowEnvironment: WindowEnvironmentModifier {
        WindowEnvironmentModifier(
            apiClient: apiClient,
            appState: appState,
            artifactService: artifactService,
            artifactStore: artifactStore,
            claimFocusState: claimFocusState,
            claimStore: claimStore,
            conversationService: conversationService,
            documentStore: documentStore,
            entityService: entityService,
            entityStore: entityStore,
            errorService: errorService,
            executionObserver: executionObserver,
            featureManager: featureManager,
            importService: importService,
            kgCurationService: kgCurationService,
            kgFocusState: kgFocusState,
            libraryManager: libraryManager,
            renditionService: renditionService,
            researchService: researchService,
            savedSearchService: savedSearchService,
            storageService: storageService,
            viewSettings: viewSettings,
            windowState: windowState,
            workflowStore: workflowStore,
            workflowStreamService: workflowStreamService
        )
    }
}
