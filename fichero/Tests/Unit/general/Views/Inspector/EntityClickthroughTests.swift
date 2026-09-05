@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// A statement leads to its source; a name leads to everything (#4672).
///
/// Daniel, 2026-09-04: clicking an SVO statement in the biography or entity
/// editor must land on the source with the passage lit; the inspector must
/// show the quote a statement is drawn from; a person's name must lead to
/// every source that mentions them. The plumbing existed — the typed source
/// cursor, the passage latch, the scoped search — but three surfaces never
/// called it, called the wrong bus, or overrode the fixed path with the
/// broken one. See agent-work/design/entity-clickthrough-fabel-review.md.
@MainActor
struct EntityClickthroughTests {

    // MARK: - Biography sentences are claims, not prose soup

    private func claim(
        id: String? = "c1", verb: String? = "otorgó", object: String? = "poder"
    ) -> Components.Schemas.KnowledgeClaim {
        var value = Components.Schemas.KnowledgeClaim(id: id, text: "t")
        value.predicateVerb = verb
        value.objectPhrase = object
        return value
    }

    @Test("each biography sentence keeps hold of the claim it renders")
    func sentencesCarryTheirClaims() {
        let pairs = EntityDigestView.biographySentences(
            entityName: "Andrés",
            claims: [claim(id: "a"), claim(id: "b", verb: "compareció", object: "ante mí")]
        )
        #expect(pairs.count == 2)
        #expect(pairs[0].sentence == "Andrés otorgó poder.")
        #expect(pairs[0].claim.id == "a")
        // Second and later sentences use the pronoun, as the prose always did.
        #expect(pairs[1].sentence == "they compareció ante mí.")
        #expect(pairs[1].claim.id == "b")
    }

    @Test("a claim with neither verb nor object produces no sentence")
    func emptyClaimsAreSkippedNotPadded() {
        let pairs = EntityDigestView.biographySentences(
            entityName: "Andrés",
            claims: [claim(verb: nil, object: nil), claim(id: "real")]
        )
        #expect(pairs.count == 1)
        #expect(pairs[0].claim.id == "real")
        // The skipped claim must not have consumed the "first sentence names
        // the entity" slot — the surviving sentence still leads with the name.
        #expect(pairs[0].sentence.hasPrefix("Andrés"))
    }

    // MARK: - The three repaired click paths call the cursor

    @Test("the biography renders per-sentence claim links, not one dead blob")
    func biographyIsClickable() throws {
        let digest = try AppSource.code("Views/Inspector/Knowledge/EntityDigestView.swift")
        #expect(digest.contains("biographyAttributed"))
        #expect(digest.contains("OpenURLAction"))
        // The handler must land on the shared cursor — the same bus the
        // provenance rows post to — not a second addressing scheme.
        #expect(digest.contains("claimSourceNavigationState?.request(request)"))
    }

    @Test("the digest header's name leads to every source, like #882's")
    func digestNameFiresScopedSearch() throws {
        let digest = try AppSource.code("Views/Inspector/Knowledge/EntityDigestView.swift")
        let header = try #require(
            digest.components(separatedBy: "private var headerSection").dropFirst().first
        )
        #expect(String(header.prefix(1200)).contains("entitySearchState?.request("))
    }

    @Test("the Ontology browser's navigate closure navigates, not just focuses")
    func ontologyClosurePostsTheSourceRequest() throws {
        let detail = try AppSource.code(
            "Views/Library/ViewModes/Graph/Ontology/OntologyBrowser+Detail.swift"
        )
        let closure = try #require(
            detail.components(separatedBy: "onNavigateToSource: { claim in").dropFirst().first
        )
        // Focus alone assigns properties on a shared object and navigates
        // nowhere — the #4666 defect, which survived here as an injected
        // override preempting the card's fixed path.
        #expect(String(closure.prefix(900)).contains("claimSourceNavigationState?.request("))
    }

    // MARK: - Attestations are navigable, not just counted (#4672)

    private func multiSourceClaim() -> Components.Schemas.KnowledgeClaim {
        var row = Components.Schemas.KnowledgeClaim(id: "c9", text: "t")
        row.sourceDocumentId = "doc-primary"
        row.sourcePageLabel = "533r"
        row.sourceExcerpt = "otorgamos poder cumplido"
        row.sourceCharStart = 61
        row.sourceCharEnd = 101
        row.sourceIds = ["doc-second", "doc-primary", "doc-third", ""]
        row.sourcePageLabels = ["12v"]
        return row
    }

    @Test("every attested place becomes a row, primary first with its quote")
    func attestationRowsCarryTheirAnchors() {
        let rows = ClaimSummaryCard.attestations(for: multiSourceClaim())
        // doc-primary repeated in sourceIds is one attestation, not two;
        // the empty id is nothing at all.
        #expect(rows.map(\.documentId) == ["doc-primary", "doc-second", "doc-third"])
        #expect(rows[0].isPrimary)
        #expect(rows[0].quote == "otorgamos poder cumplido")
        #expect(rows[0].charStart == 61)
        // Pages zip index-wise with their source ids; a missing label is
        // nil, never invented.
        #expect(rows[1].pageLabel == "12v")
        #expect(rows[2].pageLabel == nil)
        // Only the primary anchor exists in the model — additional rows must
        // not claim offsets or quotes they do not have.
        #expect(rows[1].quote == nil)
        #expect(rows[1].charStart == nil)
    }

    @Test("a single-source claim is one attestation, so no list renders")
    func singleSourceStaysSingle() {
        var row = Components.Schemas.KnowledgeClaim(id: "c1", text: "t")
        row.sourceDocumentId = "doc-only"
        #expect(ClaimSummaryCard.attestations(for: row).count == 1)
        // No source at all (a manually-asserted claim, #2019) → no rows.
        #expect(ClaimSummaryCard.attestations(
            for: Components.Schemas.KnowledgeClaim(id: "c2", text: "t")
        ).isEmpty)
    }

    @Test("also-extracted-by is attribution: labels come through, junk does not")
    func alsoExtractedByParses() throws {
        var row = Components.Schemas.KnowledgeClaim(id: "c3", text: "t")
        #expect(ClaimSummaryCard.alsoExtractedBy(row) == nil)
        row.metadata = .init(additionalProperties: try .init(
            unvalidatedValue: ["also_extracted_by": ["apple/apple-intelligence", ""]]
        ))
        #expect(ClaimSummaryCard.alsoExtractedBy(row) == ["apple/apple-intelligence"])
    }

    @Test("each attestation row navigates to ITS page, not always the primary")
    func attestationRowsNavigateIndividually() throws {
        let details = try AppSource.code(
            "Views/Library/ViewModes/Graph/Ontology/Claim/ClaimSummaryCard+Details.swift"
        )
        let list = try #require(
            details.components(separatedBy: "var attestationList: some View").dropFirst().first
        )
        let body = String(list.prefix(2500))
        #expect(body.contains("documentId: attestation.documentId"))
        #expect(body.contains("claimSourceNavigationState?.request(request)"))
    }

    @Test("the provenance badges open the drawer where the evidence lives")
    func badgesAreADoor() throws {
        let details = try AppSource.code(
            "Views/Library/ViewModes/Graph/Ontology/Claim/ClaimSummaryCard+Details.swift"
        )
        let badges = try #require(
            details.components(separatedBy: "var provenanceBadges: some View").dropFirst().first
        )
        #expect(String(badges.prefix(1200)).contains("isExpanded = true"))
    }

    // MARK: - Corroboration reaches the prose

    @Test("corroboration count reads both key spellings and both types")
    func corroborationCountReads() throws {
        var row = Components.Schemas.KnowledgeClaim(id: "c", text: "t")
        #expect(EntityDigestView.corroborationCount(of: row) == nil)
        row.metadata = .init(additionalProperties: try .init(
            unvalidatedValue: ["corroboration_count": 2]
        ))
        #expect(EntityDigestView.corroborationCount(of: row) == 2)
        row.metadata = .init(additionalProperties: try .init(
            unvalidatedValue: ["corroborationCount": "3"]
        ))
        #expect(EntityDigestView.corroborationCount(of: row) == 3)
    }

    @Test("the inspector quote is a door, not a query")
    func inspectorQuoteOpensTheSource() throws {
        let block = try AppSource.code("Views/Inspector/Knowledge/EntityKindRow+ClaimBlock.swift")
        let button = try #require(
            block.components(separatedBy: "private func claimExcerptButton").dropFirst().first
        )
        let body = String(button.prefix(2200))
        #expect(body.contains("claimSourceNavigationState?.request("))
        // The old behaviour fired a library text-search for the quote's own
        // words. Comment-stripped scan, so this line can't re-trip on prose.
        #expect(!body.contains("entitySearchState?.request("))
    }
}
