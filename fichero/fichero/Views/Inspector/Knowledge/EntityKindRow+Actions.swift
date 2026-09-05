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

    /// Double-click / "Open Source": take the reader to the EXACT page the
    /// claim came from, with the passage highlighted (#1864/#4393/#4666).
    ///
    /// This used to focus the claim and then call `onNavigateToSource`, whose
    /// host handler (`navigateToSourcePage`) only re-selects the source FILE in
    /// the library/preview — no page, no highlight — so a claim you opened
    /// landed on page 1 of the file, not where it was actually stated. The
    /// complete "trace to source" cursor (`ClaimSourceNavigationState` →
    /// `handleOpenClaimSource`) already resolves the page-child to its parent,
    /// scrolls the reader to the page and lights the span; it is the SAME
    /// cursor the claim quote-excerpt and the Ontology browser (#4666) post to.
    /// Route through it here so every claim surface traces back the one way.
    ///
    /// `onClaimTap`, when a host wired it (the reader's own Claims tab), already
    /// owns claim opening — so defer to the legacy path there rather than
    /// double-navigating.
    func openClaim(claimId: String, sourceDocumentId: String?) {
        if onClaimTap == nil,
           let sourceDocumentId,
           let claimSourceNavigationState,
           let request = sourceNavigationRequest(
               claimId: claimId,
               claim: claimById[claimId],
               sourceDocumentId: sourceDocumentId,
               sourcePageLabel: claimById[claimId]?.sourcePageLabel ?? item.sourcePageLabel,
               sourceExcerpt: nil
           ) {
            claimSourceNavigationState.request(request)
            return
        }
        // Fallback: no source cursor available (or a host owns claim taps) —
        // keep the previous behavior so nothing regresses.
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
