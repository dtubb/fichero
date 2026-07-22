import FicheroAPIClient
import Foundation
import OSLog

extension AnnotationService {
    /// Load annotations for a document into `annotations`. Never throws — on failure
    /// `annotations` is cleared and `error` is set so the tab can show an empty state.
    func load(documentId: String) async {
        await load(query: .init(documentId: documentId))
    }

    func load(pageId: String) async {
        await load(query: .init(pageId: pageId))
    }

    func load(folderId: String) async {
        await load(query: .init(folderId: folderId))
    }

    private func load(
        query: Operations.ListAnnotationsApiAnnotationsGet.Input.Query
    ) async {
        syncLibraryPath()
        isLoading = true
        error = nil
        defer { isLoading = false }

        do {
            let response = try await client.api.listAnnotationsApiAnnotationsGet(.init(
                query: query
            ))
            guard case .ok(let okResponse) = response else {
                logger.warning("List annotations returned non-OK response")
                error = "Annotations unavailable"
                annotations = []
                return
            }
            let decoded = try okResponse.body.json
            // List items arrive as untyped containers (backend `items: list[Any]`);
            // DocumentAnnotation decodes them directly (carrying document/page/folder
            // ids). Scope is already enforced by the query above.
            annotations = decoded.items.compactMap { annotation(from: $0) }
        } catch {
            if error.isCancellationError { return }   // superseded — not a failure; keep state, no log
            // Backend may not be wired yet during parallel development — degrade
            // to an empty list rather than crashing the inspector (#1276).
            logger.warning("Failed to load annotations: \(error.localizedDescription, privacy: .public)")
            self.error = "Could not load annotations"
            annotations = []
        }
    }
}
