@testable import Fichero
import Foundation
import XCTest

/// The map lens plots the right library's claims, for the right document, and
/// says which places it could not place (Daniel, 2026-09-04: the map "doesn't
/// really map").
///
/// The map itself was never the problem — `KGMapView` has been a real MapKit
/// surface since #1267. It was asking the wrong library, over the wrong scope,
/// for data that (see `agent-work/specs/map-lens-needs-coordinates.md`) no
/// extraction path writes coordinates into.
@MainActor
final class MapLensScopeTests: XCTestCase {

    private static func appSource(_ relativePath: String) throws -> String {
        try String(contentsOf: AppSource.root().appendingPathComponent(relativePath), encoding: .utf8)
    }

    /// `globalLibrary` is the library holding the RESERVED id, not the current
    /// one. Every surface that reached for it answered about a library the
    /// window was not showing — #4461, the Node Graph this morning, and these
    /// two.
    func testTheMapAndTimelineAskTheirOwnLibrary() throws {
        for path in [
            "Views/Library/ViewModes/Graph/KGMapView.swift",
            "Views/Library/ViewModes/Graph/KGTimelineView.swift"
        ] {
            let source = try Self.appSource(path)
            XCTAssertTrue(
                source.contains("@Environment(EntityService.self) private var entityService"),
                "\(path) must take the surface's own service"
            )
            XCTAssertTrue(
                source.contains("guard let service = entityService"),
                "\(path) must prefer it over the global-library lookup"
            )
            XCTAssertFalse(
                source.contains("library.entityService.listClaims"),
                "\(path) still lists claims through the reserved-id library"
            )
        }
    }

    /// A reader tab titled "Map" that plots the first 500 claims in the
    /// LIBRARY is not this document's map — and the document being read need
    /// not be among them.
    func testTheReaderScopesBothSurfacesToItsDocument() throws {
        let surface = try Self.appSource("Views/Reader/Knowledge/DocumentKGSurface.swift")
        let mapCall = try XCTUnwrap(
            surface.components(separatedBy: "KGMapView(").dropFirst().first
        )
        XCTAssertTrue(
            String(mapCall.prefix(400)).contains("sourceDocumentId: documentId"),
            "The reader's Map tab must ask for THIS document's claims."
        )
        let timelineCall = try XCTUnwrap(
            surface.components(separatedBy: "KGTimelineView(").dropFirst().first
        )
        XCTAssertTrue(
            String(timelineCall.prefix(400)).contains("sourceDocumentId: documentId")
        )
    }

    /// Places with no coordinate are LISTED, never approximated onto the map.
    /// A pin is a claim about where something was, and a reader has no way to
    /// discover that a confident-looking one was a guess.
    func testUnplacedPlacesAreNamedRatherThanCounted() throws {
        let map = try Self.appSource("Views/Library/ViewModes/Graph/KGMapView.swift")
        XCTAssertTrue(map.contains("private var unplacedNames: [String]"))
        XCTAssertTrue(map.contains("accessibilityIdentifier(\"kgMap.unplaced\")"))
        XCTAssertTrue(
            map.contains("Named in the text, with no coordinate to plot"),
            "The panel must say what it is a list OF."
        )
    }

    /// The geocoder's offline gazetteer must stay a curated list of real
    /// places. If a coordinate for a Chocó settlement ever appears in it, it
    /// came from a source or it did not belong there — see the spec.
    func testTheGazetteerWasNotSeededFromRecollection() throws {
        let repoRoot = try AppSource.root()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
        let geo = try String(
            contentsOf: repoRoot
                .appendingPathComponent("fichero-server/src/fichero_server/media/geo.py"),
            encoding: .utf8
        )
        for place in ["condoto", "tamana", "andagoya", "istmina", "quibdo"] {
            XCTAssertFalse(
                geo.lowercased().contains("\"\(place)\""),
                """
                \(place) entered the gazetteer. That is only correct if its \
                coordinate came from a real gazetteer (GeoNames CO, Nominatim) \
                rather than from a model's recollection — if it did, delete \
                this assertion and record the source beside the entry.
                """
            )
        }
    }
}
