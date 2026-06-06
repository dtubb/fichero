import FicheroAPIClient
import SwiftUI

// Entity detail panel + per-entity claim loading for OntologyBrowser (#1703).
extension OntologyBrowser {
    // MARK: - Entity Detail Panel

    var entityDetailPanel: some View {
        Group {
            if let entityId = selectedEntityId,
               let entity = entities.first(where: { $0.id == entityId }) {
                EntityDetailView(
                    entity: entity,
                    claims: entityClaims,
                    isLoadingClaims: isLoadingClaims,
                    onNavigateToSource: { claim in
                        ClaimSummaryCard.postOpenClaimSource(for: claim)
                    }
                )
                // `.task(id: entityId)` re-keys on selection change so
                // each entity's claims re-fetch — was previously a bare
                // `.task` that only fired on first appear, leaving the
                // claim list stuck on the first entity's claims even as
                // the header updated. (#965)
                .task(id: entityId) {
                    await loadEntityClaims(entity: entity)
                }
                .onReceive(NotificationCenter.default.publisher(for: .ficheroClaimDeleted)) { _ in
                    Task { await loadEntityClaims(entity: entity) }
                }
                .onReceive(NotificationCenter.default.publisher(for: .ficheroClaimUpdated)) { _ in
                    Task { await loadEntityClaims(entity: entity) }
                }
            } else {
                emptyDetailState
            }
        }
        .frame(minWidth: 250)
    }

    var emptyDetailState: some View {
        VStack(spacing: 12) {
            Image(systemName: "person.crop.rectangle.stack")
                .font(.system(size: 36))
                .foregroundColor(.secondary)

            Text("No Entity Selected")
                .font(.headline)

            Text("Select an entity to view its details")
                .font(.subheadline)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding()
    }

    func loadEntityClaims(entity: Components.Schemas.KnowledgeEntity) async {
        isLoadingClaims = true

        do {
            let library = LibraryManager.shared.globalLibrary!
            let service = library.entityService
            guard let entityId = entity.id else {
                entityClaims = []
                isLoadingClaims = false
                return
            }
            let sourceDocIds = Set((entity.sourceSupports ?? []).compactMap { $0.sourceDocumentId })
            if sourceDocIds.isEmpty {
                entityClaims = []
                isLoadingClaims = false
                return
            }

            var merged: [String: Components.Schemas.KnowledgeClaim] = [:]
            for docId in sourceDocIds {
                let response = try await service.documentKnowledgeGraph(
                    documentId: docId,
                    includeChildren: true
                )
                for claim in response.claims where (claim.entityIds ?? []).contains(entityId) {
                    if let claimId = claim.id {
                        merged[claimId] = claim
                    }
                }
            }
            entityClaims = merged.values.sorted {
                ($0.createdAt ?? Date.distantPast) > ($1.createdAt ?? Date.distantPast)
            }
        } catch {
            entityClaims = []
        }

        isLoadingClaims = false
    }
}
