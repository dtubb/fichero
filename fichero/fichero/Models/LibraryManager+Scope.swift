import Foundation

// MARK: - Owning-library resolution (#4306 / #4461)

extension LibraryManager {
    /// The open library that vends `service`, matched by object IDENTITY.
    ///
    /// This is the one answer to "which library is this surface in?" for a view
    /// that was environment-injected with a library's service but not with the
    /// library itself. A document-scoped surface that instead reaches for
    /// `globalLibrary` gets *a* real answer from the wrong scope — #4306:
    /// translate invoked `artifact.translate` on the global library's actions
    /// service while the inspected document lived elsewhere, so every translate
    /// from a non-global library errored against a database where the document
    /// did not exist.
    ///
    /// Identity, not id or path: the service object a view holds IS the one its
    /// library built, so the match cannot drift the way two parallel notions of
    /// "current library" can. Returns nil rather than falling back to global —
    /// a caller that cannot name its library must fail visibly, not quietly
    /// operate on another one.
    func library(owningService service: AnyObject) -> LibraryReference? {
        openLibraries.first { reference in
            reference.vendedServices.contains { $0 === service }
        }
    }

    /// The open library rooted at `path`, or nil when no open library is.
    func library(atPath path: String) -> LibraryReference? {
        openLibraries.first { $0.url.path == path }
    }
}

extension LibraryManager.LibraryReference {
    /// Every eagerly-built per-library service object, in declaration order.
    /// Only reference types belong here — identity is the whole point.
    ///
    /// EXHAUSTIVE on purpose, not curated. A curated subset is a derived value
    /// nothing maintains: the day a view is injected with the one service that
    /// was left out, `library(owningService:)` returns nil and the surface
    /// silently loses its scope — with nothing to notice, because the omission
    /// looks identical to "no library open". `DocumentScopeGuardTests` reads
    /// the `let …Service/Store/Client` declarations off `LibraryReference` and
    /// fails if any is missing from this list, so adding a service to the
    /// library without adding it here breaks the suite rather than the app.
    ///
    /// The `lazy var` observable stores are deliberately absent: reading one
    /// here would CONSTRUCT it for every open library on every lookup, making
    /// a scope resolution build stores nobody asked for. Each of those stores
    /// wraps a service that is in this list, and resolves to the same library.
    var vendedServices: [AnyObject] {
        [
            apiClient,
            ficheroClient,
            documentStore,
            savedSearchService,
            bookmarkService,
            searchService,
            conversationService,
            chatService,
            workflowStore,
            workflowService,
            workflowStreamService,
            importService,
            documentService,
            storageService,
            providerService,
            modelService,
            artifactService,
            entityService,
            kgCurationService,
            activityService,
            batchService,
            automationService,
            chainService,
            researchService,
            noteService,
            annotationService,
            actionsService
        ]
    }
}
