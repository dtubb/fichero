@testable import Fichero
import XCTest

/// Completes coverage of LinkType / SpatialLink / SpatialConnection.linkType.
/// MindPalaceLinkTypeTests exercises some `fallback` cases and two
/// connectionType branches; this pins the untested surface: the Codable
/// decode path, the full `isSolid` table, the composite SpatialLink.id, the
/// remaining fallback synonyms, and the remaining connectionType mappings.
final class LinkTypeStyleTests: XCTestCase {

    private func decodeLinkType(_ raw: String) throws -> LinkType {
        try JSONDecoder().decode(LinkType.self, from: Data("\"\(raw)\"".utf8))
    }

    /// Build a SpatialConnection (decode-only type) from its wire form.
    private func decodeConnection(connectionType: String,
                                  linkSubtype: String?) throws -> SpatialConnection {
        let subtypeLine = linkSubtype.map { "\"linkSubtype\": \"\($0)\"," } ?? ""
        let json = Data("""
        {
            \(subtypeLine)
            "roomId": "r",
            "sourceNodeId": "s",
            "targetNodeId": "t",
            "connectionType": "\(connectionType)"
        }
        """.utf8)
        return try JSONDecoder().decode(SpatialConnection.self, from: json)
    }

    // MARK: - Decode path (init(from:) → rawValue then fallback)

    func testDecodeExactRawValues() throws {
        XCTAssertEqual(try decodeLinkType("citation"), .citation)
        XCTAssertEqual(try decodeLinkType("parent_child"), .parentChild)
        XCTAssertEqual(try decodeLinkType("user_drawn"), .userDrawn)
        XCTAssertEqual(try decodeLinkType("unknown"), .unknown)
    }

    /// A value that is NOT a rawValue routes through fallback(), so a predicate
    /// like "cites" decodes to .citation and a truly novel value to .related.
    func testDecodeUnknownRoutesThroughFallback() throws {
        XCTAssertEqual(try decodeLinkType("cites"), .citation)
        XCTAssertEqual(try decodeLinkType("totally_new_predicate"), .related)
    }

    // MARK: - fallback synonyms not covered elsewhere

    func testFallbackSynonyms() {
        XCTAssertEqual(LinkType.fallback(for: "pictured_in"), .depicts)
        XCTAssertEqual(LinkType.fallback(for: "shown_in"), .depicts)
        XCTAssertEqual(LinkType.fallback(for: "mentions"), .mentions)
        XCTAssertEqual(LinkType.fallback(for: "supersedes"), .supersedes)
        XCTAssertEqual(LinkType.fallback(for: "parent"), .parentChild)
        XCTAssertEqual(LinkType.fallback(for: "child"), .parentChild)
        XCTAssertEqual(LinkType.fallback(for: "manual"), .userDrawn)
        // Case-insensitive + empty/unknown default.
        XCTAssertEqual(LinkType.fallback(for: "REPLACES"), .supersedes)
        XCTAssertEqual(LinkType.fallback(for: ""), .related)
    }

    // MARK: - isSolid table (fully untested elsewhere)

    func testIsSolidTable() {
        for kind in [LinkType.citation, .depicts, .parentChild, .contradicts, .supersedes] {
            XCTAssertTrue(kind.isSolid, "\(kind) should be solid")
        }
        for kind in [LinkType.mentions, .related, .userDrawn, .unknown] {
            XCTAssertFalse(kind.isSolid, "\(kind) should be dashed")
        }
    }

    // MARK: - SpatialLink composite id

    func testSpatialLinkCompositeId() {
        let link = SpatialLink(sourceId: "a", targetId: "b", linkType: .parentChild)
        XCTAssertEqual(link.id, "a|b|parent_child")
        XCTAssertEqual(link.weight, 1.0)   // default
        XCTAssertNil(link.label)
    }

    // MARK: - SpatialConnection.linkType remaining branches

    func testConnectionLinkTypeFromConnectionType() throws {
        XCTAssertEqual(try decodeConnection(connectionType: "semantic", linkSubtype: nil).linkType, .related)
        XCTAssertEqual(try decodeConnection(connectionType: "ontological", linkSubtype: nil).linkType, .parentChild)
        XCTAssertEqual(try decodeConnection(connectionType: "user_drawn", linkSubtype: nil).linkType, .userDrawn)
        // Unrecognized connectionType decodes to .unknown → linkType .unknown.
        XCTAssertEqual(try decodeConnection(connectionType: "bogus", linkSubtype: nil).linkType, .unknown)
    }

    /// An empty linkSubtype must be ignored so the connectionType mapping wins.
    func testConnectionEmptySubtypeIgnored() throws {
        let conn = try decodeConnection(connectionType: "evidentiary", linkSubtype: "")
        XCTAssertEqual(conn.linkType, .citation)
    }
}
