import FicheroAPIClient
import OSLog
import SwiftUI

// The grouping / text-digest pipeline for KnowledgeGraphInspectorSection, plus
// the small value types it produces. Split out of the core file to stay within
// SwiftLint's type/file-length budgets.
extension KnowledgeGraphInspectorSection {
    // Promoted `private` → internal: called from kgFilterMenu in +Toolbar.
    func setHidden(_ kind: EntityKind, hidden: Bool) {
        var set = hiddenKinds
        if hidden { set.insert(kind) } else { set.remove(kind) }
        hiddenKindsCSV = set.map(\.rawValue).sorted().joined(separator: ",")
    }

    // Promoted `private` → internal: called from `body` in the core file.
    /// The single grouping pass (#3863). Builds the claim lookup, the grouped +
    /// sorted sections, the flat ordered-claim-id list, and the text digest (with
    /// its markdown AttributedStrings pre-rendered) in ONE pass, into @State the
    /// body reads. Runs on data change, not on every render/selection click.
    func recomputeGrouped() {
        let byId = Dictionary(uniqueKeysWithValues: claims.compactMap { claim -> (String, Components.Schemas.KnowledgeClaim)? in
            guard let id = claim.id else { return nil }
            return (id, claim)
        })
        claimsById = byId

        let groups = groupedSections(using: byId)
        grouped = groups

        orderedClaimIds = Self.orderedClaimIds(from: groups)

        textDigest = groups.map { kind, items in
            let entries = items.map { item -> TextDigestEntry in
                // SwiftUI markdown bold for the entity name — rendered ONCE here, not
                // per render inside the digest ForEach (#3863).
                let raw = Self.digestMarkup(
                    displayName: item.displayName,
                    contexts: [item.context] + item.extraClaims.map(\.context)
                )
                let attributed = (try? AttributedString(markdown: raw)) ?? AttributedString(raw)
                return TextDigestEntry(id: item.id, displayName: item.displayName, kind: kind, attributed: attributed)
            }
            return (kind, entries)
        }
    }

    /// The flat claim-id order the selection/highlight code walks: each item's
    /// primary claim followed by its extra claims, in section order. Pure so the
    /// ordering invariant is testable independent of the view. (#3863)
    static func orderedClaimIds(from groups: [(EntityKind, [GroupedItem])]) -> [String] {
        groups.flatMap { _, items in
            items.flatMap { item in [item.claimId] + item.extraClaims.map(\.claimId) }
        }
    }

    /// The digest line's markdown: the entity name bolded, then its contexts joined
    /// with "; ". Pure so the format is testable without rendering. (#3863)
    static func digestMarkup(displayName: String, contexts: [String]) -> String {
        "**\(displayName)** \(contexts.joined(separator: "; "))"
    }

    /// Build the visible, sorted `(kind, [GroupedItem])` sections from the canonical
    /// groups + a claim lookup. Split out of `recomputeGrouped` for length; called
    /// only from there.
    private func groupedSections(
        using byId: [String: Components.Schemas.KnowledgeClaim]
    ) -> [(EntityKind, [GroupedItem])] {
        let hidden = hiddenKinds
        return canonicalGroups.compactMap { group -> (EntityKind, [GroupedItem])? in
            guard let kind = EntityKind(groupKind: group.kind), !hidden.contains(kind) else { return nil }
            var items: [GroupedItem] = []
            for item in group.items {
                guard let firstClaimId = item.claimIds.first else { continue }
                let firstClaim = byId[firstClaimId]
                let primaryContext = (item.description ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
                let excerpt = (item.sourceExcerpt ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
                let context = !primaryContext.isEmpty
                    ? primaryContext
                    : (!excerpt.isEmpty ? excerpt : (firstClaim?.text ?? item.canonicalName))
                let extraClaims: [GroupedItem.ExtraClaim] = item.claimIds.dropFirst().compactMap { claimId in
                    let claim = byId[claimId]
                    return GroupedItem.ExtraClaim(
                        claimId: claimId,
                        context: claim?.text ?? context,
                        sourceDocumentId: claim?.sourceDocumentId ?? item.sourceDocumentId,
                        sourcePageLabel: claim?.sourcePageLabel ?? item.sourcePageLabel,
                        sourceExcerpt: claim?.sourceExcerpt ?? item.sourceExcerpt
                    )
                }
                items.append(GroupedItem(
                    entityId: item.entityId,
                    claimId: firstClaimId,
                    displayName: item.canonicalName,
                    context: context,
                    aliases: item.aliases,
                    confidence: firstClaim?.confidence,
                    sourceDocumentId: item.sourceDocumentId,
                    sourcePageLabel: item.sourcePageLabel,
                    sourceExcerpt: item.sourceExcerpt,
                    extraClaims: extraClaims
                ))
            }
            guard !items.isEmpty else { return nil }
            // #4394: was `confidence ?? 0` on both sides, which ranked a claim
            // nobody scored exactly where it ranked a claim the model scored
            // 0.0 — "we don't know" rendered as "we know it is worthless", and
            // the two then interleaved under the name tiebreak. `ordersBefore`
            // keeps unrecorded out of the ranking instead of giving it a value.
            let sorted = items.sorted { lhs, rhs in
                if let ordered = ConfidenceBand.ordersBefore(lhs.confidence, rhs.confidence) {
                    return ordered
                }
                return lhs.displayName.localizedCaseInsensitiveCompare(rhs.displayName) == .orderedAscending
            }
            return (kind, sorted)
        }
    }

    // Promoted `private` → internal: read by the toolbar menus in +Toolbar and
    // contextMenuTargetClaims in +Actions.
    var selectedClaims: [Components.Schemas.KnowledgeClaim] {
        orderedClaimIds.compactMap { claimId in
            guard claimSelection.contains(claimId) else { return nil }
            return claimsById[claimId]
        }
    }

    // MARK: - Text digest data

    // Promoted `private` → internal: referenced by the core file's `textDigest`
    // @State and by textDigestView in +Views.
    struct TextDigestEntry: Identifiable {
        let id: String
        let displayName: String
        let kind: EntityKind
        // The bold-name markdown rendered once in `recomputeGrouped`, not per render.
        let attributed: AttributedString
    }

    private struct EntityAccumulator {
        let kind: EntityKind
        let displayName: String
        var svoLines: [String]
    }

    // Promoted `private` → internal: used by claimMergeActionMenu in +Toolbar.
    /// A claim paired with its NON-optional id, so merge menus can `ForEach` over
    /// `\.id` without a body-side `filter { $0.id != nil }` or optional identity.
    struct IdentifiedClaim: Identifiable {
        let id: String
        let claim: Components.Schemas.KnowledgeClaim
    }

    // Promoted `private` → internal: called from claimMergeActionMenu in +Toolbar.
    func identifiedClaims(
        from claims: [Components.Schemas.KnowledgeClaim]
    ) -> [IdentifiedClaim] {
        claims.compactMap { claim in claim.id.map { IdentifiedClaim(id: $0, claim: claim) } }
    }
}
