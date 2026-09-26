@testable import Fichero
import Foundation
import FicheroAPIClient
import Testing

/// #3863 — the KG inspector's grouping pipeline moved off the render path into
/// `recomputeGrouped`. These lock the pure derivations it now precomputes, so the
/// selection order and digest format can't silently drift.
@MainActor
struct KGSectionGroupingTests {

    private func item(_ claimId: String, extras: [String] = []) -> GroupedItem {
        GroupedItem(
            claimId: claimId,
            displayName: claimId.uppercased(),
            context: "ctx-\(claimId)",
            aliases: [],
            extraClaims: extras.map {
                GroupedItem.ExtraClaim(
                    claimId: $0,
                    context: "ctx-\($0)",
                    sourceDocumentId: nil,
                    sourcePageLabel: nil,
                    sourceExcerpt: nil
                )
            }
        )
    }

    @Test("orderedClaimIds = each item's primary claim then its extras, in section order")
    func orderedClaimIdsFlattening() {
        let groups: [(EntityKind, [GroupedItem])] = [
            (.other, [item("c1", extras: ["c1b"]), item("c2")]),
            (.other, [item("c3")])
        ]
        #expect(KnowledgeGraphInspectorSection.orderedClaimIds(from: groups) == ["c1", "c1b", "c2", "c3"])
    }

    @Test("orderedClaimIds is empty for no groups")
    func orderedClaimIdsEmpty() {
        #expect(KnowledgeGraphInspectorSection.orderedClaimIds(from: []).isEmpty)
    }

    // MARK: - #4834/#4852: each sentence is its own claim, its own click target

    private func svoClaim(
        id: String?, subject: String?, verb: String?, object: String?
    ) -> Components.Schemas.KnowledgeClaim {
        var value = Components.Schemas.KnowledgeClaim(id: id, text: "t")
        value.subjectCanonical = subject
        value.predicateVerb = verb
        value.objectPhrase = object
        return value
    }

    /// Claim ids carried by the digest's in-prose sentence links, same
    /// idiom as `EntitySourceGroupsLinkTests.linkedClaimIds`.
    private func linkedClaimIds(_ attributed: AttributedString) -> [String] {
        attributed.runs.compactMap { run in
            guard let link = run.link,
                  link.scheme == KnowledgeGraphInspectorSection.digestClaimLinkScheme
            else { return nil }
            return link.host
        }
    }

    @Test("every complete-triple claim becomes its own clickable sentence")
    func everyClaimIsItsOwnLink() {
        let attributed = KnowledgeGraphInspectorSection.digestAttributedString(
            displayName: "Ada",
            claims: [
                svoClaim(id: "c1", subject: "Ada", verb: "invented", object: "X"),
                svoClaim(id: "c2", subject: "Ada", verb: "met", object: "Y")
            ]
        )
        #expect(linkedClaimIds(attributed) == ["c1", "c2"])
    }

    /// #4835-class rule, restated for this surface: the claim's OWN subject,
    /// never the group's displayName standing in for one.
    @Test("a digest sentence's subject is the claim's own subject, not the group name")
    func sentenceUsesTheClaimsOwnSubject() {
        let attributed = KnowledgeGraphInspectorSection.digestAttributedString(
            displayName: "Ada Lovelace",
            claims: [svoClaim(id: "c1", subject: "Charles Babbage", verb: "met", object: "Ada")]
        )
        #expect(String(attributed.characters).contains("Charles Babbage met Ada."))
    }

    /// #4852: whole sentences only, joined with a space — the old "; "-joined
    /// mix of fragments and full sentences produced ".;" wherever a sentence
    /// met the separator. `svoTriple` sentences always end in one period, so
    /// no output may ever contain ".;" or a doubled space.
    @Test("digest output never contains '.;' or a doubled separator")
    func noSemicolonPeriodArtifact() {
        let attributed = KnowledgeGraphInspectorSection.digestAttributedString(
            displayName: "Ada",
            claims: [
                svoClaim(id: "c1", subject: "Ada", verb: "invented", object: "X"),
                svoClaim(id: "c2", subject: "Ada", verb: "met", object: "Y"),
                svoClaim(id: "c3", subject: "Ada", verb: "wrote", object: "Z")
            ]
        )
        let text = String(attributed.characters)
        #expect(!text.contains(".;"))
        #expect(!text.contains("  "))
    }

    /// A claim missing any part of the triple is skipped — not padded, not
    /// rendered as a subject-less fragment.
    @Test("a claim without a complete SVO triple is skipped, not padded")
    func incompleteTripleIsSkipped() {
        let attributed = KnowledgeGraphInspectorSection.digestAttributedString(
            displayName: "Ada",
            claims: [
                svoClaim(id: "complete", subject: "Ada", verb: "invented", object: "X"),
                svoClaim(id: "no-object", subject: "Ada", verb: "met", object: nil)
            ]
        )
        #expect(linkedClaimIds(attributed) == ["complete"])
    }

    /// A claim with no id has nowhere honest to link to — same precision
    /// rule as `EntitySourceGroupsView.buildClauseAttributedString`.
    @Test("a claim with no id renders no link")
    func claimWithNoIdHasNoLink() {
        let attributed = KnowledgeGraphInspectorSection.digestAttributedString(
            displayName: "Ada",
            claims: [svoClaim(id: nil, subject: "Ada", verb: "invented", object: "X")]
        )
        #expect(linkedClaimIds(attributed).isEmpty)
    }

    /// Each digest sentence link resolves through the SAME request bus and `.both` destination as
    /// the biography sentence and the claim-excerpt button (`kg.read.source-request-declares-intent`).
    @Test("the digest's sentence links resolve to a source reveal at .both")
    func digestLinksResolveAtBothDestination() throws {
        var claim = svoClaim(id: "c1", subject: "Ada", verb: "invented", object: "X")
        claim.sourceDocumentId = "doc-1"
        claim.sourcePageLabel = "4"
        let url = try #require(URL(string: "\(KnowledgeGraphInspectorSection.digestClaimLinkScheme)://c1"))
        let action = KnowledgeGraphInspectorSection.digestLinkAction(for: url, claimsById: ["c1": claim])
        guard case .reveal(let request) = action else {
            // `Issue.record` RETURNS an Issue, so `return Issue.record(...)` is a
            // non-void return from a void test. Record, then return separately.
            Issue.record("expected .reveal, got \(action)")
            return
        }
        #expect(request.destination == .both)
        #expect(request.documentId == "doc-1")
        #expect(request.claimId == "c1")
    }

    @Test("the [Edit] link opens the editor for that claim, and unknown links are discarded")
    func editLinkAndUnknownLinks() throws {
        let claim = svoClaim(id: "c1", subject: "Ada", verb: "invented", object: "X")
        let claims = ["c1": claim]
        let edit = try #require(URL(string: "\(KnowledgeGraphInspectorSection.digestClaimEditLinkScheme)://c1"))
        #expect(KnowledgeGraphInspectorSection.digestLinkAction(for: edit, claimsById: claims) == .edit(claimId: "c1"))
        let unknownClaim = try #require(URL(string: "\(KnowledgeGraphInspectorSection.digestClaimLinkScheme)://nope"))
        #expect(KnowledgeGraphInspectorSection.digestLinkAction(for: unknownClaim, claimsById: claims) == .discard)
        let foreign = try #require(URL(string: "https://c1"))
        #expect(KnowledgeGraphInspectorSection.digestLinkAction(for: foreign, claimsById: claims) == .discard)
        // A claim with no source document has nowhere honest to reveal.
        let noSource = try #require(URL(string: "\(KnowledgeGraphInspectorSection.digestClaimLinkScheme)://c1"))
        #expect(KnowledgeGraphInspectorSection.digestLinkAction(for: noSource, claimsById: claims) == .discard)
    }
}
