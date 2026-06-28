@testable import Fichero
import Foundation
import XCTest

/// Tests for the Representation enum — the switchable per-page views (#2264).
/// Locks: every case carries a non-empty title + SF Symbol, `id` mirrors the
/// raw value, only image/markdown are renderable today, and the artifact-type
/// mapping matches the backend tool outputs.
final class RepresentationTests: XCTestCase {

    func testAllCasesHaveTitleSystemImageAndStableId() {
        for representation in Representation.allCases {
            XCTAssertFalse(representation.title.isEmpty, "\(representation) title")
            XCTAssertFalse(representation.systemImage.isEmpty, "\(representation) symbol")
            XCTAssertEqual(representation.id, representation.rawValue)
        }
    }

    func testCaseCountIsStable() {
        // image, markdown, html, svg, table, worldMap, globe
        XCTAssertEqual(Representation.allCases.count, 7)
    }

    func testOnlyImageAndMarkdownAreRenderable() {
        XCTAssertTrue(Representation.image.isRenderable)
        XCTAssertTrue(Representation.markdown.isRenderable)
        for representation in [Representation.html, .svg, .table, .worldMap, .globe] {
            XCTAssertFalse(representation.isRenderable, "\(representation) should not be renderable yet")
        }
    }

    func testFromArtifactTypeMapsKnownTypes() {
        XCTAssertEqual(Representation.from(artifactType: "conversion"), .markdown)
        XCTAssertEqual(Representation.from(artifactType: "transcription"), .markdown)
        XCTAssertEqual(Representation.from(artifactType: "table"), .table)
        XCTAssertEqual(Representation.from(artifactType: "geo"), .worldMap)
    }

    func testFromArtifactTypeReturnsNilForUnknown() {
        XCTAssertNil(Representation.from(artifactType: "image"))
        XCTAssertNil(Representation.from(artifactType: "unknown"))
        XCTAssertNil(Representation.from(artifactType: ""))
    }
}
