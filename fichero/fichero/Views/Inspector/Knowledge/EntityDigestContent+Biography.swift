import FicheroAPIClient
import SwiftUI

// Split out of EntityDigestView.swift (#4896 lint follow-up: type_body_length
// 365/250, file_length 784/400) — a MOVE only, no behaviour change. See the
// doc comment on `EntityDigestContent` in EntityDigestView.swift for the
// access-level rule this split follows.
extension EntityDigestContent {
    var biographySection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Biography")
                .font(.headline)
                .padding(.bottom, 4)

            if isLoading && claims.isEmpty {
                ProgressView()
            } else if claims.isEmpty {
                Text("No claims available to reconstruct a biography.")
                    .foregroundStyle(.secondary)
                    .italic()
            } else {
                // Each sentence IS a claim, and a claim knows its page — so
                // each sentence is a door (Daniel, 2026-09-04: "click on an
                // SVO statement in the biography and be taken to the source
                // … with the relevant passage highlighted"). Rendered as one
                // prose run with per-sentence links so the paragraph still
                // reads as a biography, not a list.
                Text(biographyAttributed)
                    .font(.body)
                    .lineSpacing(6)
                    .textSelection(.enabled)
                    .environment(\.openURL, OpenURLAction { url in
                        guard let claimId = url.host ?? url.pathComponents.dropFirst().first
                        else { return .discarded }
                        // #4833: the "[Edit]" run opens the same
                        // InlineClaimEditor the row's context menu does — a
                        // separate, explicit affordance from the sentence's
                        // own reveal link.
                        if url.scheme == Self.claimEditLinkScheme {
                            guard claims.contains(where: { $0.id == claimId }) else { return .discarded }
                            editingBiographyClaimId = claimId
                            return .handled
                        }
                        guard url.scheme == Self.claimLinkScheme,
                              let claim = claims.first(where: { $0.id == claimId }),
                              // #4834 priority-2 surface: the biography
                              // sentence IS the statement; both highlight
                              // channels, selection unchanged.
                              let request = ClaimSourceRequest.request(for: claim, destination: .both)
                        else { return .discarded }
                        claimSourceNavigationState?.request(request)
                        return .handled
                    })
                    .popover(isPresented: Binding(
                        get: { editingBiographyClaimId != nil },
                        set: { if !$0 { editingBiographyClaimId = nil } }
                    )) {
                        if let claimId = editingBiographyClaimId,
                           let claim = claims.first(where: { $0.id == claimId }) {
                            InlineClaimEditor(
                                claim: claim,
                                onCancel: { editingBiographyClaimId = nil },
                                onSave: { updated in
                                    spliceUpdatedClaim(updated)
                                    editingBiographyClaimId = nil
                                }
                            )
                            .padding(8)
                        }
                    }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    /// Splice a `ClaimStore.patch`-returned claim into this view's own
    /// `claims` — never a reload (#4833). `ClaimStore.patch` does not bump
    /// `changeToken` (it already spliced the STORE'S copy), so the
    /// `.onChange(of: claimStore?.changeToken)` resync above would not pick
    /// this up on its own; this is the local half of the same splice.
    private func spliceUpdatedClaim(_ updated: Components.Schemas.KnowledgeClaim) {
        guard let id = updated.id, let index = claims.firstIndex(where: { $0.id == id }) else { return }
        claims[index] = updated
    }

    /// Custom scheme for in-prose claim links; never leaves the view.
    static let claimLinkScheme = "fichero-claim"

    /// Custom scheme for the biography's per-sentence EDIT affordance
    /// (#4833) — same shape as `KnowledgeGraphInspectorSection`'s digest:
    /// a second, explicit link right after the sentence link, reachable by
    /// the same native link-in-text keyboard/VoiceOver focus.
    static let claimEditLinkScheme = "fichero-claim-edit"

    /// The biography prose with each sentence carrying a link to its claim.
    /// A claim with no id stays plain text — a link that goes nowhere is
    /// worse than no link.
    private var biographyAttributed: AttributedString {
        let pairs = Self.biographySentences(claims: claims)
        guard !pairs.isEmpty else {
            return AttributedString("No biography data available.")
        }
        var prose = AttributedString()
        var first = true
        for (sentence, claim) in pairs {
            if !first { prose += AttributedString(" ") }
            first = false
            var run = AttributedString(sentence)
            // URLComponents, not a string-built URL: this is an INTERNAL link
            // scheme for tappable prose, and the raw-networking guards ban
            // string URL construction outright rather than guessing intent.
            var linkParts = URLComponents()
            linkParts.scheme = Self.claimLinkScheme
            linkParts.host = claim.id
            if claim.id != nil, let url = linkParts.url {
                run.link = url
                // Prose, not a wall of hyperlink-blue: keep body color and
                // mark tappability with a subtle underline.
                run.foregroundColor = .primary
                run.underlineStyle = .single
            }
            prose += run
            // A sentence more than one extraction agrees on says so, in the
            // prose, quietly — corroboration is stored on the claim and was
            // shown nowhere the biography reader could see it (#4672).
            if let count = Self.corroborationCount(of: claim), count > 0 {
                // Same number the provenance badge shows ("\(count)x
                // corroborated") — two surfaces, one figure.
                var marker = AttributedString(" ×\(count)")
                marker.foregroundColor = .secondary
                prose += marker
            }
            // #4833: the edit affordance, one per sentence — plain text
            // ("[Edit]"), not a bare glyph, so VoiceOver reads it as "Edit"
            // rather than the character's own name.
            if let claimId = claim.id {
                var editLinkParts = URLComponents()
                editLinkParts.scheme = Self.claimEditLinkScheme
                editLinkParts.host = claimId
                if let editURL = editLinkParts.url {
                    var editRun = AttributedString(" [Edit]")
                    editRun.link = editURL
                    editRun.foregroundColor = .secondary
                    editRun.underlineStyle = .single
                    prose += editRun
                }
            }
        }
        return prose
    }

    /// How many OTHER extractions corroborate this claim (`also_extracted_by`
    /// rows counted at write time). Mirrors the provenance badge's read so
    /// the two surfaces cannot disagree about the same number.
    static func corroborationCount(
        of claim: Components.Schemas.KnowledgeClaim
    ) -> Int? {
        guard let metadata = claim.metadata?.additionalProperties.value else { return nil }
        return metadata["corroboration_count"] as? Int
            ?? Int(metadata["corroboration_count"] as? String ?? "")
            ?? metadata["corroborationCount"] as? Int
            ?? Int(metadata["corroborationCount"] as? String ?? "")
    }

    /// The per-sentence pairing behind the prose — static so the mapping is
    /// testable without mounting the view. One sentence per claim with a
    /// COMPLETE SVO triple; claims without one are skipped, not padded and
    /// never given a guessed subject (#4835).
    static func biographySentences(
        claims: [Components.Schemas.KnowledgeClaim]
    ) -> [(sentence: String, claim: Components.Schemas.KnowledgeClaim)] {
        var pairs: [(String, Components.Schemas.KnowledgeClaim)] = []
        for claim in claims {
            // #4835: the claim's OWN subject, never the page entity's name —
            // `ClaimSummaryCard.svoTriple(for:)` is the SAME resolver
            // `provenanceSummary` (EntityDigestContent+Provenance.swift)
            // already uses for this exact screen; one source of truth, not a
            // second resolver. It requires a COMPLETE triple (subject/verb/
            // object all present, neither subject nor object an opaque id) —
            // a claim missing any of the three is skipped rather than
            // rendered with a guessed subject (a pronoun, or the page
            // entity's name). Re-centring (the page entity becomes the
            // subject via a verb's inverse-table entry) is a later,
            // engine-side plan step, not this one.
            guard let svo = ClaimSummaryCard.svoTriple(for: claim) else { continue }

            // No bracketed citation (#4393). It was built from the STORAGE
            // filename and looked up only in `currentDocuments`, so it printed
            // an internal identifier AND vanished non-deterministically when
            // that document was not loaded — a citation that changes depending
            // on what else is on screen is worse than none. Provenance belongs
            // on the row, where it can be navigated to.
            pairs.append(("\(svo.subject) \(svo.verb) \(svo.object).", claim))
        }
        return pairs
    }
}
