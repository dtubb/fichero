@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// Clicking a statement takes you to the page it was read from (#4666).
///
/// Daniel, 2026-09-04, on the SVO browser: the statements "seem to not be
/// applying." Three separate reasons a click did nothing:
///
///   1. The plain row click called `focusClaim()`, which assigns four
///      properties on a shared focus object and navigates nowhere.
///   2. `postOpenClaimSource` refused to issue the request at all unless the
///      claim's source page happened to be in the folder currently listed —
///      which, for a claim read off page 533 of a bundle while you browse the
///      entity list, it never is.
///   3. Even when the request went through, the highlight rode
///      `claimFocusState`, whose sync is match-or-CLEAR and is not re-run when
///      the page's text arrives. Following a claim changes the document, so
///      the text always arrived after the request, and the highlight was
///      cleared before it could match. 787b624c2 solved exactly this for
///      search with a latch; claims now use the same one.
@MainActor
struct ClaimSourceLandingTests {

    // MARK: - The latch

    @Test("a claim with a quote latches a passage anchor before navigating")
    func aClaimWithAQuoteLatchesAnAnchor() {
        ReaderPassageFocus.reset()
        defer { ReaderPassageFocus.reset() }

        ReaderPassageFocus.record(
            ReaderPassageAnchor(
                documentId: "page-533r",
                text: "Andres xptoval Hernandez Varela cañistin",
                charStart: 61,
                charEnd: 101
            )
        )
        let latched = ReaderPassageFocus.latest
        #expect(latched?.documentId == "page-533r")
        #expect(latched?.charStart == 61)
        // The matcher's shape, shared with the search path — one definition of
        // "where does this land in the text".
        #expect(latched?.highlightInfo["excerpt"] as? String
                == "Andres xptoval Hernandez Varela cañistin")
    }

    @Test("the latch is consumed by the document that used it, not by another")
    func theLatchIsConsumedByItsOwnDocument() {
        ReaderPassageFocus.reset()
        defer { ReaderPassageFocus.reset() }

        ReaderPassageFocus.record(
            ReaderPassageAnchor(documentId: "page-533r", text: "x", charStart: 0, charEnd: 1)
        )
        ReaderPassageFocus.consume(documentId: "page-999")
        #expect(ReaderPassageFocus.latest != nil, "another page must not eat this anchor")
        ReaderPassageFocus.consume(documentId: "page-533r")
        #expect(ReaderPassageFocus.latest == nil)
    }

    // MARK: - The wiring

    /// The claim path mints and latches an anchor, the way the search path
    /// does — wired, not merely wireable.
    @Test("following a claim source records and posts a passage anchor")
    func theClaimPathUsesThePassageSeam() throws {
        let source = try String(
            contentsOf: AppSource.root()
                .appendingPathComponent(
                    "Views/Shell/ContentView/ContentView+ClaimPassageLanding.swift"
                ),
            encoding: .utf8
        )
        #expect(source.contains("ReaderPassageFocus.record("))
        #expect(source.contains("ReaderPassageAnchor.kindKey"))
        #expect(source.contains("ReaderPassageAnchor.searchPassageKind"))

        let handler = try String(
            contentsOf: AppSource.root()
                .appendingPathComponent("Views/Shell/ContentView/ContentView+StateEvents.swift"),
            encoding: .utf8
        )
        let body = try #require(
            handler.components(separatedBy: "func handleOpenClaimSource() {")
                .dropFirst().first
        )
        let scope = String(body.prefix(4000))
        // Recorded BEFORE the reveal, posted after: an anchor recorded after
        // the navigation is an anchor the newly-mounted reader never sees.
        let recordIndex = try #require(scope.range(of: "recordClaimPassageAnchor(request)"))
        let revealIndex = try #require(scope.range(of: "await revealResolvedSource(request)"))
        let postIndex = try #require(scope.range(of: "postClaimPassageAnchor(documentId: docId)"))
        #expect(recordIndex.lowerBound < revealIndex.lowerBound)
        #expect(revealIndex.lowerBound < postIndex.lowerBound)
    }

    /// The plain click navigates. It used to only set focus properties.
    @Test("a plain click on a statement goes to its source")
    func aPlainClickNavigatesToTheSource() throws {
        let source = try String(
            contentsOf: AppSource.root()
                .appendingPathComponent(
                    "Views/Library/ViewModes/Graph/Ontology/Claim/ClaimSummaryCardView.swift"
                ),
            encoding: .utf8
        )
        let tap = try #require(
            source.components(separatedBy: ".onTapGesture {").dropFirst().first
        )
        #expect(String(tap.prefix(1500)).contains("navigateToSource()"))
    }

    /// Source with `//` comment bodies removed, so a guard tests what the code
    /// DOES rather than what its comments say it used to do.
    static func codeOnly(_ source: String) -> String {
        source
            .components(separatedBy: .newlines)
            .filter { !$0.trimmingCharacters(in: .whitespaces).hasPrefix("//") }
            .joined(separator: "\n")
    }

    /// The source page does not have to be in the folder you are looking at.
    @Test("following a claim does not require its page to be in the listing")
    func theListingDoesNotGateTheSourceOpen() throws {
        let source = try String(
            contentsOf: AppSource.root()
                .appendingPathComponent(
                    "Views/Library/ViewModes/Graph/Ontology/Claim/ClaimSummaryCard+Details.swift"
                ),
            encoding: .utf8
        )
        let function = try #require(
            source.components(separatedBy: "func postOpenClaimSource(").dropFirst().first
        )
        // CODE only. The function's body opens with a comment explaining that
        // it used to gate on `documentStore.currentDocuments` — so a raw scan
        // matched the very sentence describing the fix, and this assertion
        // could never have passed as written. Same class as the reader's
        // passage-anchor guard, which failed on its own explanation.
        #expect(!Self.codeOnly(String(function.prefix(1200))).contains("currentDocuments"))
    }
}

/// A geocoded pin is drawn as a guess, because that is what it is (#4668).
///
/// The engine now writes a coordinate onto extracted claims — which is what
/// makes the map plot anything at all — and marks each one `inferred` with
/// `created_by: "geocoder"`. Without the classifier reading that, every
/// gazetteer hit would render as a solid pin: the archive asserting a
/// precision it never had, with no way for a reader to tell.
@MainActor
struct ClaimGeoProvenanceTests {

    private func place(
        basis: Components.Schemas.EvidenceBasis,
        createdBy: String?,
        lat: Double? = 2.4448
    ) -> Components.Schemas.EvidentialPlace {
        var value = Components.Schemas.EvidentialPlace(label: "Popayán", basis: basis)
        value.lat = lat
        value.lon = -76.6147
        value.createdBy = createdBy
        return value
    }

    private func claim(
        places: [Components.Schemas.EvidentialPlace]
    ) -> Components.Schemas.KnowledgeClaim {
        var row = Components.Schemas.KnowledgeClaim(id: "c1", text: "Pedro travelled to Popayán.")
        row.claimGeo = Components.Schemas.GeoPoint(lat: 2.4448, lon: -76.6147)
        row.placeValues = places
        return row
    }

    @Test("a geocoded point renders as inferred")
    func aGeocodedPointIsInferred() {
        let row = claim(places: [place(basis: .inferred, createdBy: "geocoder")])
        #expect(KGSpatial.isGeocoded(row))
        #expect(KGSpatial.provenance(for: row) == .inferred)
    }

    @Test("a hand-placed point stays asserted")
    func aHandPlacedPointIsAsserted() {
        let row = claim(places: [place(basis: .asserted, createdBy: "extractor")])
        #expect(!KGSpatial.isGeocoded(row))
        #expect(KGSpatial.provenance(for: row) == .asserted)
    }

    @Test("a place row with no coordinate does not make the claim geocoded")
    func aPlaceWithoutACoordinateIsNotAGeocode() {
        // A source-anchored region ("the province of Popayán") is inferred and
        // carries no point; it must not demote a real fix beside it.
        let row = claim(places: [place(basis: .inferred, createdBy: "extractor", lat: nil)])
        #expect(!KGSpatial.isGeocoded(row))
    }

    @Test("a claim with no coordinate at all is inferred and unplottable")
    func aClaimWithNoPointIsInferred() {
        var row = Components.Schemas.KnowledgeClaim(id: "c2", text: "Pedro travelled.")
        row.claimGeo = nil
        #expect(KGSpatial.provenance(for: row) == .inferred)
    }
}
