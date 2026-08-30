@testable import Fichero
import FicheroAPIClient
import XCTest

/// ClaimAttribution(claim:) — deriving who asserts a claim from the engine's
/// speaker fields (#3448/#1123). A claim with a speaker entity or a free
/// speaker name is person-asserted; otherwise the document/article itself is
/// the assertor. These lock that mapping so the Knowledge tab reads attribution
/// consistently.
final class ClaimAttributionTests: XCTestCase {

    private func claim(
        speakerName: String? = nil,
        speakerEntityId: String? = nil,
        claimSpeaker: String? = nil,
        page: String? = nil
    ) -> Components.Schemas.KnowledgeClaim {
        var c = Components.Schemas.KnowledgeClaim(
            id: "claim-1",
            text: "Ada says the engine weaves patterns",
            subjectCanonical: "engine",
            predicateVerb: "weaves",
            objectPhrase: "patterns"
        )
        c.speakerName = speakerName
        c.speakerEntityId = speakerEntityId
        c.claimSpeaker = claimSpeaker
        c.sourcePageLabel = page
        return c
    }

    func testNoSpeakerIsDocumentAsserted() {
        let a = ClaimAttribution(claim: claim(claimSpeaker: "the article"))
        XCTAssertEqual(a.kind, .document)
        XCTAssertEqual(a.name, "the article")
    }

    func testDocumentAssertedFallsBackToDefaultName() {
        let a = ClaimAttribution(claim: claim())
        XCTAssertEqual(a.kind, .document)
        XCTAssertEqual(a.name, "This document")
    }

    func testSpeakerNameIsPersonAsserted() {
        let a = ClaimAttribution(claim: claim(speakerName: "Ada Lovelace"))
        XCTAssertEqual(a.kind, .person)
        XCTAssertEqual(a.name, "Ada Lovelace")
    }

    func testSpeakerEntityIsPersonAsserted() {
        let a = ClaimAttribution(claim: claim(speakerEntityId: "ent-9", claimSpeaker: "Ada"))
        XCTAssertEqual(a.kind, .person)
        // Prefer the free name, then the formatted claimSpeaker.
        XCTAssertEqual(a.name, "Ada")
    }

    func testBlankSpeakerNameIsNotPerson() {
        let a = ClaimAttribution(claim: claim(speakerName: "   "))
        XCTAssertEqual(a.kind, .document)
    }

    func testCarriesVerbatimAndLocation() {
        let a = ClaimAttribution(claim: claim(speakerName: "Ada", page: "12"))
        XCTAssertEqual(a.verbatimSpan, "Ada says the engine weaves patterns")
        XCTAssertEqual(a.locationLabel, "p. 12")
    }
}
