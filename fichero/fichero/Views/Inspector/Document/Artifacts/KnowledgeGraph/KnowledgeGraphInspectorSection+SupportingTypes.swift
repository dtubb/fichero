import FicheroAPIClient
import OSLog
import SwiftUI

// Standalone value types backing KnowledgeGraphInspectorSection — scope,
// confirmation, bulk-action and merge-selection helpers — plus the section's
// static list-capping utilities. Split out of the core file for file length.

// MARK: - KnowledgeGraphInspectorSection utilities

extension KnowledgeGraphInspectorSection {
    static let groupVisibleCap = 10

    static func visibleItems<T>(_ items: [T], showingAll: Bool, cap: Int = groupVisibleCap) -> [T] {
        if showingAll || items.count <= cap { return items }
        return Array(items.prefix(cap))
    }

    static func showAllButtonTitle(itemCount: Int, showingAll: Bool, cap: Int = groupVisibleCap) -> String? {
        guard itemCount > cap else { return nil }
        return showingAll ? "Show less" : "Show all (\(itemCount))"
    }

    static func isKindStored(_ kind: EntityKind, in csv: String) -> Bool {
        csv.split(separator: ",").contains(Substring(kind.rawValue))
    }
}

enum InspectorClaimDocumentScope {
    case page
    case folder

    var label: String {
        switch self {
        case .page:
            return "This page only"
        case .folder:
            return "This folder only"
        }
    }

    var confirmationTarget: String {
        switch self {
        case .page:
            return "this page"
        case .folder:
            return "this folder"
        }
    }

    func pruneScope(documentId: String) -> KGCurationService.PruneTrivialScope {
        switch self {
        case .page:
            return .document(documentId: documentId)
        case .folder:
            return .folder(folderId: documentId)
        }
    }
}

struct PendingPruneConfirmation: Identifiable {
    let id = UUID()
    let scope: KGCurationService.PruneTrivialScope
    let title: String
    let message: String
}

struct PendingClaimDeleteConfirmation: Identifiable {
    let claims: [Components.Schemas.KnowledgeClaim]

    var id: String {
        claims.compactMap(\.id).sorted().joined(separator: "|")
    }

    var title: String {
        if claims.count == 1, let claim = claims.first {
            return "Delete \"\(claim.displayMergeName)\"?"
        }
        return "Delete \(claims.count) claims?"
    }

    var message: String {
        if claims.count == 1 {
            return "This removes the claim from the knowledge graph. Related entities stay in place."
        }
        return "This removes the selected claims from the knowledge graph. Related entities stay in place."
    }
}

enum InspectorClaimBulkAction: Equatable {
    case approve
    case reject
    case suppress

    var verb: String {
        switch self {
        case .approve: return "Approved"
        case .reject: return "Rejected"
        case .suppress: return "Suppressed"
        }
    }

    var curationState: Components.Schemas.ClaimCurationState {
        switch self {
        case .approve: return .curated
        case .reject, .suppress: return .rejected
        }
    }
}

struct InspectorClaimBulkSelection {
    struct MergePlan: Equatable, Identifiable {
        let survivorId: String
        let absorbedClaimIds: [String]
        let survivorName: String
        let claimCount: Int

        var id: String {
            "\(survivorId):\(absorbedClaimIds.sorted().joined(separator: ","))"
        }
    }

    static func libraryWideSuppressRules(
        for claims: [Components.Schemas.KnowledgeClaim]
    ) -> [Components.Schemas.ClaimRuleCreateRequest] {
        var seen = Set<String>()
        return claims.compactMap { claim in
            let subject = claim.subjectCanonical?.trimmingCharacters(in: .whitespacesAndNewlines)
            let predicate = claim.predicateVerb?.trimmingCharacters(in: .whitespacesAndNewlines)
            let object = claim.objectPhrase?.trimmingCharacters(in: .whitespacesAndNewlines)
            let normalizedSubject = (subject?.isEmpty == false) ? subject : nil
            let normalizedPredicate = (predicate?.isEmpty == false) ? predicate : nil
            let normalizedObject = (object?.isEmpty == false) ? object : nil
            guard normalizedSubject != nil || normalizedPredicate != nil || normalizedObject != nil else {
                return nil
            }

            let dedupeKey = [
                normalizedSubject?.lowercased() ?? "",
                normalizedPredicate?.lowercased() ?? "",
                normalizedObject?.lowercased() ?? ""
            ].joined(separator: "|")
            guard seen.insert(dedupeKey).inserted else { return nil }

            // Follow-up (#1763): prune-trivial when the selection is entirely is-a/copula claims.
            return Components.Schemas.ClaimRuleCreateRequest(
                action: .disable,
                matchPredicateVerb: normalizedPredicate,
                matchSubjectName: normalizedSubject,
                matchObjectPhrase: normalizedObject,
                suppressIsACopulas: false,
                reason: "Bulk suppress from inspector",
                createdBy: "human"
            )
        }
    }

    /// Merge plan using the heuristic survivor (`mergeSurvivor`) as the
    /// destination — the default/recommended choice.
    static func mergePlan(
        for claims: [Components.Schemas.KnowledgeClaim]
    ) -> MergePlan? {
        guard let survivorId = mergeSurvivor(in: claims)?.id else { return nil }
        return mergePlan(for: claims, survivorId: survivorId)
    }

    /// Merge plan with a caller-chosen survivor so the user can pick which
    /// claim is the merge DESTINATION (#2499). `survivorId` must be one of
    /// `claims`; the rest fold into it. Same validity gates as the heuristic
    /// path (2+ claims, none already merged, all have IDs).
    static func mergePlan(
        for claims: [Components.Schemas.KnowledgeClaim],
        survivorId: String
    ) -> MergePlan? {
        guard claims.count > 1,
              claims.allSatisfy({ $0.mergedIntoId == nil }),
              let survivor = claims.first(where: { $0.id == survivorId })
        else {
            return nil
        }

        let claimIds = claims.compactMap(\.id)
        guard claimIds.count == claims.count else { return nil }

        let absorbedClaimIds = claimIds.filter { $0 != survivorId }
        guard !absorbedClaimIds.isEmpty else { return nil }

        return MergePlan(
            survivorId: survivorId,
            absorbedClaimIds: absorbedClaimIds,
            survivorName: survivor.displayMergeName,
            claimCount: claims.count
        )
    }

    static func mergeSurvivor(
        in claims: [Components.Schemas.KnowledgeClaim]
    ) -> Components.Schemas.KnowledgeClaim? {
        claims.sorted { lhs, rhs in
            let lhsCorroboration = lhs.corroborationCount ?? 0
            let rhsCorroboration = rhs.corroborationCount ?? 0
            if lhsCorroboration != rhsCorroboration {
                return lhsCorroboration > rhsCorroboration
            }

            let lhsWeighted = lhs.weightedCorroborationCount ?? 0
            let rhsWeighted = rhs.weightedCorroborationCount ?? 0
            if lhsWeighted != rhsWeighted {
                return lhsWeighted > rhsWeighted
            }

            let lhsSupport = lhs.sourceSupports?.count ?? 0
            let rhsSupport = rhs.sourceSupports?.count ?? 0
            if lhsSupport != rhsSupport {
                return lhsSupport > rhsSupport
            }

            let lhsName = lhs.displayMergeName
            let rhsName = rhs.displayMergeName
            if lhsName.count != rhsName.count {
                return lhsName.count > rhsName.count
            }

            let lexical = lhsName.localizedCaseInsensitiveCompare(rhsName)
            if lexical != .orderedSame {
                return lexical == .orderedAscending
            }
            return (lhs.id ?? "") < (rhs.id ?? "")
        }.first
    }
}

extension Components.Schemas.KnowledgeClaim {
    var displayMergeName: String {
        let text = text.trimmingCharacters(in: .whitespacesAndNewlines)
        if !text.isEmpty {
            return text
        }

        let pieces = [subjectCanonical, predicateVerb, objectPhrase]
            .compactMap { $0?.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
        if !pieces.isEmpty {
            return pieces.joined(separator: " ")
        }

        return id ?? "Untitled claim"
    }
}
