import FicheroAPIClient
import Foundation
import Observation
import OSLog

private let logger = Logger(subsystem: "app.fichero.fichero", category: "LibraryClaimsModel")

/// Folder-scoped claim loading for the claims library view — a claim is a NODE
/// that flows through the same library the way a document does, so this is the
/// claim analogue of the document listing that populates the table.
///
/// It reuses the EXISTING claim seam (`EntityService.listClaims`) rather than a
/// new endpoint: the folder's claims are `source_document_id == folderId` with
/// `includeDescendants` so a folder shows every claim beneath it, exactly as the
/// table shows a folder's documents recursively. Library-wide scope (Phase 3, the
/// sidebar "Claims" section) is the same call with `folderId == nil`.
@MainActor
@Observable
final class LibraryClaimsModel {
    private(set) var claims: [Components.Schemas.KnowledgeClaim] = []
    private(set) var isLoading = false
    private(set) var loadError: String?

    /// Bumped per load so a superseded fetch (an earlier folder) drops its result
    /// instead of clobbering the current one — the same generation guard the
    /// loove service and other progressive loaders use.
    private var generation = 0

    private let service: EntityService

    init(service: EntityService) {
        self.service = service
    }

    /// Load the claims for a folder scope. `folderId == nil` loads library-wide.
    /// `includeDescendants` makes a folder show every claim beneath it (recursive),
    /// matching how the table lists a folder's documents.
    func load(folderId: String?, includeDescendants: Bool = true, limit: Int = 25000) async {
        generation += 1
        let mine = generation
        isLoading = true
        loadError = nil
        do {
            let fetched = try await service.listClaims(
                sourceDocumentId: folderId,
                includeDescendants: includeDescendants,
                limit: limit
            )
            guard mine == generation else { return }  // superseded by a newer load
            claims = fetched
            isLoading = false
        } catch {
            guard mine == generation else { return }
            logger.error("Claims load failed for folder \(folderId ?? "<library>", privacy: .public): \(error.localizedDescription)")
            claims = []
            loadError = error.localizedDescription
            isLoading = false
        }
    }
}
