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

    /// Delete the given claims (spec: kg-tables `claim.delete`). Each is one audited,
    /// reversible backend action — the SAME `deleteClaim` call `ClaimStore.delete`
    /// makes, so the server change-stream still fires for every other claim surface.
    /// The rows then leave THIS list in place (`crud.in-place`), never a full reload.
    func delete(claimIds: [String]) async throws {
        guard !claimIds.isEmpty else { return }
        // Bounded-concurrent + prune-only-successes (spec: kg-tables kg.scale.bulk-
        // correctness): a partial failure removes exactly the rows that were deleted,
        // never leaving a phantom row, and N deletes don't run N serial round-trips.
        // Interim until a batch-delete endpoint (#4643).
        let svc = service
        let succeeded = await BulkDelete.succeeding(ids: claimIds) { id in
            do { try await svc.deleteClaim(id); return true } catch { return false }
        }
        claims = Self.removing(claimIds: succeeded, from: claims)
        if succeeded.count < claimIds.count {
            throw BulkDeleteError.partial(deleted: succeeded.count, requested: claimIds.count)
        }
    }

    /// The composite key a claims table reloads on: BOTH the active library AND
    /// the folder scope. The library-wide Claims row keeps `folderId == nil`
    /// before AND after a library switch, so keying the reload on `folderId`
    /// alone never refired across libraries and the table showed the PREVIOUS
    /// library's claims (spec: panes-magnifiers-workspaces F5). Folding the
    /// library id in makes a switch change the key even when the folder scope
    /// does not. `nonisolated` + pure so the reset rule is unit-testable off-main.
    nonisolated static func reloadKey(libraryId: UUID, folderId: String?) -> String {
        "\(libraryId.uuidString)|\(folderId ?? "")"
    }

    /// The pure removal rule: drop claims whose id is in `claimIds`, keep the rest.
    /// A claim with no id is never removed (absence is not a match). `nonisolated`
    /// (touches no actor state) so the in-place-delete behaviour is testable off-main.
    nonisolated static func removing(
        claimIds: [String],
        from claims: [Components.Schemas.KnowledgeClaim]
    ) -> [Components.Schemas.KnowledgeClaim] {
        let doomed = Set(claimIds)
        return claims.filter { claim in
            guard let id = claim.id else { return true }
            return !doomed.contains(id)
        }
    }
}
