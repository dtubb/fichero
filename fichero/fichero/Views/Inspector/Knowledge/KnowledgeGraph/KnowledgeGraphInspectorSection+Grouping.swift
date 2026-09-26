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

    // Promoted `private` → internal: textDigestView (+Views) calls this from
    // InlineClaimEditor's `onSave`.
    /// Splice a `ClaimStore.patch`-returned claim into THIS section's own
    /// `claims` — never a reload (#4833). This section keeps its own scoped
    /// copy (`loadState.claims`, resynced wholesale only on `changeToken`,
    /// see the core file's `.onChange`), so a store-level splice alone does
    /// not reach it; setting `claims[index]` here is what re-triggers the
    /// EXISTING `.onChange(of: claims) { recomputeGrouped() }` pipeline —
    /// itself a pure, local, no-network recomputation, not a fetch — so the
    /// row, the digest sentence and (via `claimsById`) every other reader of
    /// this section's claim lookup update from the ONE returned claim.
    func spliceUpdatedClaim(_ updated: Components.Schemas.KnowledgeClaim) {
        guard let id = updated.id, let index = claims.firstIndex(where: { $0.id == id }) else { return }
        claims[index] = updated
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
                // Bold entity name + one clickable sentence per claim —
                // rendered ONCE here, not per render inside the digest
                // ForEach (#3863).
                let itemClaimIds = [item.claimId] + item.extraClaims.map(\.claimId)
                let itemClaims = itemClaimIds.compactMap { byId[$0] }
                let attributed = Self.digestAttributedString(
                    displayName: item.displayName,
                    claims: itemClaims
                )
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

    /// Custom scheme for the digest's per-sentence claim links; never leaves
    /// the view. Same local-per-view convention as `EntityDigestView` and
    /// `EntitySourceGroupsView` — each surface owns its own scheme constant
    /// and `openURL` handler rather than sharing one across files.
    static let digestClaimLinkScheme = "fichero-claim"

    /// Custom scheme for the digest's per-sentence EDIT affordance (#4833).
    /// A sentence click still reveals the source — editing is a second,
    /// explicit link right after it, not a hidden gesture on the same text.
    /// A pencil glyph as its own tappable run is the reachable equivalent of
    /// a hover pencil for prose built from `AttributedString` runs inside
    /// ONE `Text`: it gets the same native link-in-text keyboard/VoiceOver
    /// focus as the sentence link beside it, without a per-sentence overlay
    /// view (`Text` cannot host arbitrary child views inline).
    static let digestClaimEditLinkScheme = "fichero-claim-edit"

    /// What tapping a link in the digest does (#4833/#4834), decided from the URL alone.
    enum DigestLinkAction: Equatable {
        /// The "[Edit]" run: open the inline editor for this claim.
        case edit(claimId: String)
        /// The sentence itself: reveal its source at `.both`, through the shared request bus.
        case reveal(ClaimSourceNavigationRequest)
        case discard
    }

    static func digestLinkAction(
        for url: URL, claimsById: [String: Components.Schemas.KnowledgeClaim]
    ) -> DigestLinkAction {
        guard let claimId = url.host, let claim = claimsById[claimId] else { return .discard }
        if url.scheme == digestClaimEditLinkScheme { return .edit(claimId: claimId) }
        guard url.scheme == digestClaimLinkScheme,
              let request = ClaimSourceRequest.request(for: claim, destination: .both)
        else { return .discard }
        return .reveal(request)
    }

    /// The digest line: the entity name bolded, then ONE sentence per claim,
    /// each its own clickable run linking to that claim's id (#4834/#4852 —
    /// the maintainer clicked a sentence in this exact text and nothing
    /// happened; the three small per-row buttons beside it were never what
    /// he was clicking).
    ///
    /// Each sentence is `ClaimSummaryCard.svoTriple(for:)`'s subject/verb/
    /// object — the SAME resolver the entity-digest biography uses since
    /// b6052b42a — never a guessed subject and never the page/group entity's
    /// displayName. A claim with no COMPLETE triple (subject, verb and
    /// object all present, neither an opaque id) is skipped, not padded and
    /// not rendered as a fragment.
    ///
    /// Whole sentences only, joined with a single space (#4852): the old
    /// `digestMarkup` joined raw `context` strings — a mix of verb-phrase
    /// fragments ("es llamado Antonio...") and already-punctuated full
    /// sentences — with "; ", which produced ".;" wherever a sentence met
    /// the separator. `svoTriple` sentences always end in one period, so a
    /// space is the only separator that can ever be correct here.
    static func digestAttributedString(
        displayName: String,
        claims: [Components.Schemas.KnowledgeClaim]
    ) -> AttributedString {
        let bolded = (try? AttributedString(markdown: "**\(displayName)**")) ?? AttributedString(displayName)
        var result = bolded
        for claim in claims {
            guard let svo = ClaimSummaryCard.svoTriple(for: claim), let claimId = claim.id else { continue }
            var sentence = AttributedString(" \(svo.subject) \(svo.verb) \(svo.object).")
            // URLComponents, not a string-built URL: an INTERNAL link scheme
            // for tappable prose — same construction EntityDigestView and
            // EntitySourceGroupsView use for their claim links.
            var linkParts = URLComponents()
            linkParts.scheme = digestClaimLinkScheme
            linkParts.host = claimId
            if let url = linkParts.url {
                sentence.link = url
                // Prose, not a wall of hyperlink-blue: body color + a subtle
                // underline marks tappability, mirroring the biography.
                sentence.foregroundColor = .primary
                sentence.underlineStyle = .single
                // VoiceOver reads a link's accessibility label from the run's
                // plain text by default; nothing extra is needed here — the
                // sentence text itself IS the label. Keyboard focus for an
                // AttributedString link inside `Text` is handled by SwiftUI's
                // native link-in-text focus machinery (the same path the
                // biography and source-groups links already rely on).
            }
            result += sentence

            // #4833: the edit affordance, one per sentence, reachable
            // without a right-click. Plain text ("[Edit]"), not a bare glyph
            // — VoiceOver reads a link's label from its own run text by
            // default (same as the sentence link above), and a pencil
            // character alone reads as "pencil", not "edit".
            var editLink = AttributedString(" [Edit]")
            var editLinkParts = URLComponents()
            editLinkParts.scheme = digestClaimEditLinkScheme
            editLinkParts.host = claimId
            if let editURL = editLinkParts.url {
                editLink.link = editURL
                editLink.foregroundColor = .secondary
                editLink.underlineStyle = .single
            }
            result += editLink
        }
        return result
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
