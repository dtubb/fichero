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
                        kgFocusState.focusEntity(
                            entityId: entity.id,
                            sourceDocumentId: claim.sourceDocumentId,
                            sourcePageLabel: claim.sourcePageLabel
                        )
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
                // Resync this entity's claims whenever any claim mutates —
                // ClaimStore bumps `changeToken` on every `claim.*` change event
                // fanned from the per-library change-stream (#1862/#1863),
                // replacing the retired `.ficheroClaim*` NotificationCenter bus.
                .onChange(of: claimStore.changeToken) {
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
        guard let entityId = entity.id else {
            entityClaims = []
            return
        }
        isLoadingClaims = true
        defer { isLoadingClaims = false }

        // Route through ClaimStore — the observable data layer (#3300). One
        // entity-scoped fetch (`listClaims(entityId:)`) instead of a per-source-
        // document `documentKnowledgeGraph` fan-out, and no
        // `LibraryManager.shared` singleton. The store also drives the
        // change-stream resync this view already observes (`changeToken`).
        await claimStore.loadClaims(forEntity: entityId, force: true)
        entityClaims = claimStore.claims.sorted {
            ($0.createdAt ?? Date.distantPast) > ($1.createdAt ?? Date.distantPast)
        }
    }
}
