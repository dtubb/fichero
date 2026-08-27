import Foundation
import XCTest

@testable import Fichero

/// Defensive decoding for `SpatialNodeType`: any raw value this client build
/// doesn't recognise decodes to `.unknown` rather than throwing, so a spatial
/// scene with one future node kind still loads. Pure JSON-scalar round-trips.
final class SpatialNodeTypeTests: XCTestCase {

    private func decode(_ rawJSONString: String) throws -> SpatialNodeType {
        // A bare JSON string scalar (e.g. "source") is valid top-level JSON.
        try JSONDecoder().decode(SpatialNodeType.self, from: Data("\"\(rawJSONString)\"".utf8))
    }

    func testEveryKnownRawValueDecodesToItsCase() throws {
        let cases: [(String, SpatialNodeType)] = [
            ("source", .source), ("claim", .claim), ("note", .note),
            ("entity", .entity), ("transcription", .transcription),
            ("unknown", .unknown)
        ]
        for (raw, expected) in cases {
            XCTAssertEqual(try decode(raw), expected, "raw=\(raw)")
        }
    }

    func testUnrecognisedRawValueDecodesToUnknown() throws {
        // The invariant: a future/foreign kind must NOT throw — it degrades to
        // .unknown so the whole scene still decodes.
        XCTAssertEqual(try decode("workflow"), .unknown)
        XCTAssertEqual(try decode(""), .unknown)
        XCTAssertEqual(try decode("SOURCE"), .unknown) // case-sensitive raw match
    }

    func testIconIsTotalAndNonEmpty() {
        for type in SpatialNodeType.allCases {
            XCTAssertFalse(type.icon.isEmpty, "icon for \(type)")
        }
        // Spot-check a couple views rely on.
        XCTAssertEqual(SpatialNodeType.source.icon, "doc.text")
        XCTAssertEqual(SpatialNodeType.unknown.icon, "circle")
    }
}
