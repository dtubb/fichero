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
