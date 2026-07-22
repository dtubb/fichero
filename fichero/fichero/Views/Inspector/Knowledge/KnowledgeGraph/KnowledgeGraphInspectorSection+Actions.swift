import FicheroAPIClient
import OSLog
import SwiftUI

// Load / bulk-action / merge / delete / prune handlers for
// KnowledgeGraphInspectorSection. Split out of the core file for file length.
extension KnowledgeGraphInspectorSection {
    // Promoted `private` → internal: passed as `claimContextMenuTarget` by
    // kgClaimRow in +Views.
    func contextMenuTargetClaims(
        for claim: Components.Schemas.KnowledgeClaim
    ) -> [Components.Schemas.KnowledgeClaim] {
        guard let claimId = claim.id else { return [claim] }
        if claimSelection.contains(claimId) {
            return selectedClaims
        }
        return [claim]
    }

    // Promoted `private` → internal: used by kgClaimRow (+Views) and
    // deleteActionButton (+Toolbar).
    func requestDeleteAction(for targetClaims: [Components.Schemas.KnowledgeClaim]) {
        pendingDeleteConfirmation = PendingClaimDeleteConfirmation(claims: targetClaims)
    }

    // The old modifier-key selection reducer (handleClaimTap) was retired with
    // the native-List conversion (#3425): List(selection:) owns single-click,
    // cmd/shift multi-select, and arrow-key navigation. Focus now flows from
    // focusSingleSelectedClaim on selection change.

    // Promoted `private` → internal: called from focusSingleSelectedClaim in +Views.
    func focusClaim(_ claim: Components.Schemas.KnowledgeClaim) {
        guard let claimId = claim.id else { return }
        kgFocusState.focusClaim(
            claimId: claimId,
            entityId: claim.subjectEntityId,
            sourceDocumentId: claim.sourceDocumentId,
            sourcePageLabel: claim.sourcePageLabel
        )
        onClaimSelect?(
            claimId,
            claim.sourceExcerpt,
            claim.sourceDocumentId,
            claim.sourcePageLabel,
            nil,
            nil
        )
    }

    // Promoted `private` → internal: called from `body` (+ core) and the reload
    // button in kgMiniToolbar (+Toolbar).
    func loadStatements() async {
        isLoading = true
        loadError = nil
        defer { isLoading = false }

        do {
            let response = try await entityService.documentKnowledgeGraph(
                documentId: documentId,
                includeChildren: includeChildren
            )
            claims = response.claims
            canonicalGroups = response.groups
            syncSelectionToLoadedClaims()
        } catch {
            if error.isCancellationError {
                // Task superseded by a newer page selection — not a load failure.
                return
            }
            loadError = "Couldn't load: \(error.localizedDescription)"
            claims = []
            canonicalGroups = []
            claimSelection = []
            claimSelectionAnchor = nil
        }
    }

    private func syncSelectionToLoadedClaims() {
        let validIds = Set(orderedClaimIds)
        claimSelection = claimSelection.intersection(validIds)
        if let claimSelectionAnchor, !validIds.contains(claimSelectionAnchor) {
            self.claimSelectionAnchor = nil
        }
    }

    // Promoted `private` → internal: passed as `applyClaimBulkAction` by kgClaimRow
    // (+Views) and invoked from claimBulkScopeButtons (+Toolbar).
    func applyBulkAction(
        _ action: InspectorClaimBulkAction,
        scope: InspectorEntityBulkActionScope,
        targetClaims: [Components.Schemas.KnowledgeClaim]
    ) async {
        let claimIds = targetClaims.compactMap(\.id)
        let missingIdCount = targetClaims.count - claimIds.count
        guard !claimIds.isEmpty || (action == .suppress && scope == .libraryWide) else {
            claimActionMessage = "Selected claims are missing IDs, so \(action.verb.lowercased()) was skipped."
            return
        }

        isApplyingBulkAction = true
        claimActionMessage = nil
        defer { isApplyingBulkAction = false }

        do {
            let suppressRules = action == .suppress && scope == .libraryWide
                ? InspectorClaimBulkSelection.libraryWideSuppressRules(for: targetClaims)
                : []

            if !claimIds.isEmpty {
                _ = try await kgCurationService.batchSetClaimCurationState(
                    claimIds: claimIds,
                    curationState: action.curationState
                )
            }

            if action == .suppress, scope == .libraryWide, !suppressRules.isEmpty {
                _ = try await kgCurationService.batchCreateClaimRules(suppressRules)
            }

            await loadStatements()
            claimSelection = []
            claimSelectionAnchor = nil

            if claimIds.isEmpty && suppressRules.isEmpty {
                // Nothing was actually applied — don't report a false success.
                claimActionMessage = missingIdCount > 0
                    ? "Selected claims are missing IDs, so \(action.verb.lowercased()) was skipped."
                    : "Nothing to \(action.verb.lowercased())."
            } else {
                var message = "\(action.verb) \(claimIds.count) claim"
                message += claimIds.count == 1 ? "" : "s"
                if action == .suppress, scope == .libraryWide {
                    message += " and wrote \(suppressRules.count) suppress rule"
                    message += suppressRules.count == 1 ? "" : "s"
                }
                if missingIdCount > 0 {
                    message += "; skipped \(missingIdCount) without IDs"
                }
                claimActionMessage = message
            }
        } catch {
            claimActionMessage = "Couldn't \(action.verb.lowercased()) claims: \(error.localizedDescription)"
        }
    }

    // Promoted `private` → internal: passed as `requestClaimMergeAction` by
    // kgClaimRow in +Views.
    func requestMergeAction(plan: InspectorClaimBulkSelection.MergePlan) {
        pendingMergePlan = plan
    }

    // Promoted `private` → internal: invoked from the delete alert in `body`.
    func applyDelete(_ pending: PendingClaimDeleteConfirmation) async {
        let claimIds = pending.claims.compactMap(\.id)
        let missingIdCount = pending.claims.count - claimIds.count
        guard !claimIds.isEmpty else {
            claimActionMessage = "Selected claims are missing IDs, so delete was skipped."
            pendingDeleteConfirmation = nil
            return
        }

        isApplyingBulkAction = true
        claimActionMessage = nil
        pendingDeleteConfirmation = nil
        defer { isApplyingBulkAction = false }

        do {
            for claimId in claimIds {
                try await entityService.deleteClaim(claimId)
            }
            await loadStatements()
            claimSelection = []
            claimSelectionAnchor = nil

            var message = "Deleted \(claimIds.count) claim"
            message += claimIds.count == 1 ? "" : "s"
            if missingIdCount > 0 {
                message += "; skipped \(missingIdCount) without IDs"
            }
            claimActionMessage = message
        } catch {
            inspectorClaimsLogger.error(
                "Claim delete failed for \(documentId, privacy: .public): \(error.localizedDescription, privacy: .public)"
            )
            claimActionMessage = "Couldn't delete claims: \(error.localizedDescription)"
        }
    }

    // swiftlint:disable:next todo
    // TODO(#1689): claim unmerge UI
    // Promoted `private` → internal: invoked from the merge alert in `body`.
    func applyMerge(_ plan: InspectorClaimBulkSelection.MergePlan) async {
        isApplyingBulkAction = true
        claimActionMessage = nil
        pendingMergePlan = nil
        defer { isApplyingBulkAction = false }

        do {
            _ = try await kgCurationService.mergeClaims(
                survivorId: plan.survivorId,
                absorbedIds: plan.absorbedClaimIds
            )
            await loadStatements()
            claimSelection = []
            claimSelectionAnchor = nil
            claimActionMessage = "Merged \(plan.claimCount) claims."
        } catch {
            inspectorClaimsLogger.error(
                "Claim merge failed for \(documentId, privacy: .public): \(error.localizedDescription, privacy: .public)"
            )
            claimActionMessage = "Couldn't merge claims: \(error.localizedDescription)"
        }
    }

    // Promoted `private` → internal: passed as `requestPruneTrivialAction` by
    // kgClaimRow (+Views) and invoked from pruneTrivialScopeButtons (+Toolbar).
    func requestPruneTrivialAction(_ scope: InspectorEntityBulkActionScope) {
        pendingPruneConfirmation = PendingPruneConfirmation(
            scope: pruneScope(for: scope),
            title: pruneConfirmationTitle(for: scope),
            message: pruneConfirmationMessage(for: scope)
        )
    }

    private func pruneScope(
        for scope: InspectorEntityBulkActionScope
    ) -> KGCurationService.PruneTrivialScope {
        switch scope {
        case .pageOrFolderOnly:
            return documentScope.pruneScope(documentId: documentId)
        case .libraryWide:
            return .libraryWide
        }
    }

    private func pruneConfirmationTitle(for scope: InspectorEntityBulkActionScope) -> String {
        switch scope {
        case .pageOrFolderOnly:
            return "Prune trivially-true claims in \(documentScope.confirmationTarget)?"
        case .libraryWide:
            return "Prune trivially-true claims across the whole library?"
        }
    }

    private func pruneConfirmationMessage(for scope: InspectorEntityBulkActionScope) -> String {
        switch scope {
        case .pageOrFolderOnly:
            return "This updates claim curation state for the current scope and refreshes the inspector list."
        case .libraryWide:
            return "This scans the whole library, updates matching claims, and may write a persistent suppress is-a copulas rule."
        }
    }

    // Promoted `private` → internal: invoked from the prune alert in `body`.
    func applyPruneTrivialClaims(
        scope: KGCurationService.PruneTrivialScope
    ) async {
        isPruningTrivialClaims = true
        claimActionMessage = nil
        defer {
            isPruningTrivialClaims = false
            pendingPruneConfirmation = nil
        }

        do {
            let response = try await kgCurationService.pruneTrivialClaims(scope: scope)
            await loadStatements()
            claimSelection = []
            claimSelectionAnchor = nil

            var message = "Pruned \(response.suppressedCount) trivial claim"
            if response.suppressedCount != 1 {
                message += "s"
            }
            claimActionMessage = message
        } catch {
            claimActionMessage = "Couldn't prune trivial claims: \(error.localizedDescription)"
        }
    }
}
