import FicheroAPIClient
import SwiftUI

// MARK: - EntityKindRow focus + bulk actions

extension EntityKindRow {
    func focusPrimaryClaim() {
        if let primaryClaim {
            handleClaimTap(primaryClaim)
            return
        }
        kgFocusState.focusClaim(
            claimId: item.claimId,
            entityId: item.entityId,
            sourceDocumentId: item.sourceDocumentId,
            sourcePageLabel: item.sourcePageLabel
        )
    }

    func handleClaimTap(_ claim: Components.Schemas.KnowledgeClaim) {
        if let onClaimTap {
            onClaimTap(claim)
            return
        }
        kgFocusState.focusClaim(
            claimId: claim.id,
            entityId: claim.subjectEntityId ?? item.entityId,
            sourceDocumentId: claim.sourceDocumentId ?? item.sourceDocumentId,
            sourcePageLabel: claim.sourcePageLabel ?? item.sourcePageLabel
        )
    }

    /// Double-click "open": focus the claim and navigate the reading view
    /// to its source document/page when a source is known. (#1864)
    func openClaim(claimId: String, sourceDocumentId: String?) {
        if let claim = claimById[claimId] {
            handleClaimTap(claim)
        } else {
            focusPrimaryClaim()
        }
        if let sourceDocumentId, let onNavigateToSource {
            onNavigateToSource(sourceDocumentId)
        }
    }

    @ViewBuilder
    func claimBulkContextMenu(
        for claim: Components.Schemas.KnowledgeClaim
    ) -> some View {
        claimMergeMenuSection(claim: claim)
        claimApprovalActionsSection(claim: claim)
    }

    @ViewBuilder
    private func claimMergeMenuSection(claim: Components.Schemas.KnowledgeClaim) -> some View {
        if let claimContextMenuTarget {
            let targetClaims = claimContextMenuTarget(claim)
            if let requestClaimMergeAction {
                if InspectorClaimBulkSelection.mergePlan(for: targetClaims) != nil {
                    let recommendedId = InspectorClaimBulkSelection.mergeSurvivor(in: targetClaims)?.id
                    Menu("Merge") {
                        // One destination per candidate — user picks the survivor (#2499).
                        ForEach(targetClaims.filter { $0.id != nil }, id: \.id) { candidate in
                            if let id = candidate.id,
                               let plan = InspectorClaimBulkSelection.mergePlan(
                                    for: targetClaims, survivorId: id) {
                                Button(id == recommendedId
                                    ? "Into \"\(candidate.displayMergeName)\" (Recommended)"
                                    : "Into \"\(candidate.displayMergeName)\"") {
                                    requestClaimMergeAction(plan)
                                }
                            }
                        }
                    }
                } else {
                    Button("Merge requires 2+ live claims") {}
                        .disabled(true)
                }
            }
        }
    }

    @ViewBuilder
    private func claimApprovalActionsSection(claim: Components.Schemas.KnowledgeClaim) -> some View {
        if let claimScopeLabel, let claimContextMenuTarget, let applyClaimBulkAction {
            let targetClaims = claimContextMenuTarget(claim)
            Menu("Approve") {
                claimBulkScopeButtons(
                    scopeLabel: claimScopeLabel,
                    action: .approve,
                    targetClaims: targetClaims,
                    applyClaimBulkAction: applyClaimBulkAction
                )
            }
            Menu("Reject") {
                claimBulkScopeButtons(
                    scopeLabel: claimScopeLabel,
                    action: .reject,
                    targetClaims: targetClaims,
                    applyClaimBulkAction: applyClaimBulkAction
                )
            }
            Menu("Suppress") {
                claimBulkScopeButtons(
                    scopeLabel: claimScopeLabel,
                    action: .suppress,
                    targetClaims: targetClaims,
                    applyClaimBulkAction: applyClaimBulkAction
                )
            }
            if let requestPruneTrivialAction {
                Menu("Prune trivial") {
                    Button(claimScopeLabel) {
                        requestPruneTrivialAction(.pageOrFolderOnly)
                    }
                    Button("Library-wide") {
                        requestPruneTrivialAction(.libraryWide)
                    }
                }
            }
            if let requestClaimDeleteAction {
                Button("Delete…", role: .destructive) {
                    requestClaimDeleteAction(targetClaims)
                }
            }
        }
    }

    @ViewBuilder
    func claimBulkScopeButtons(
        scopeLabel: String,
        action: InspectorClaimBulkAction,
        targetClaims: [Components.Schemas.KnowledgeClaim],
        applyClaimBulkAction: @escaping (
            InspectorClaimBulkAction,
            InspectorEntityBulkActionScope,
            [Components.Schemas.KnowledgeClaim]
        ) async -> Void
    ) -> some View {
        Button(scopeLabel) {
            Task {
                await applyClaimBulkAction(
                    action,
                    .pageOrFolderOnly,
                    targetClaims
                )
            }
        }
        Button("Library-wide") {
            Task {
                await applyClaimBulkAction(
                    action,
                    .libraryWide,
                    targetClaims
                )
            }
        }
    }
}
