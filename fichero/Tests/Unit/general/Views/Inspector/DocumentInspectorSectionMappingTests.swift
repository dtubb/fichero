@testable import Fichero
import FicheroAPIClient
import Foundation
import XCTest

/// DocumentInspector's 10→4 fold (#3434/#3454): the top switcher shows four
/// sections and derives the active one from the persisted `InspectorTab`, so the
/// focus-routing handlers (which still set a facet) keep working. These lock the
/// derivation + that Edits left the inspector.
@MainActor
final class DocumentInspectorSectionMappingTests: XCTestCase {

    private func imageDoc() -> Document {
        Document(
            id: "d1",
            parentId: nil,
            docType: .file,
            fileType: .image,
            name: "scan.png",
            path: nil,
            sequence: nil,
            bbox: nil,
            status: .completed,
            metadata: [:],
            pageContent: nil,
            createdAt: Date(),
            updatedAt: Date()
        )
    }

    func testFacetsMapToTheirSection() {
        let doc = imageDoc()
        XCTAssertEqual(DocumentInspector.section(for: .content, in: doc), .source)
        XCTAssertEqual(DocumentInspector.section(for: .info, in: doc), .source)
        XCTAssertEqual(DocumentInspector.section(for: .artifacts, in: doc), .artifacts)
        XCTAssertEqual(DocumentInspector.section(for: .knowledgeGraph, in: doc), .knowledge)
        XCTAssertEqual(DocumentInspector.section(for: .entities, in: doc), .knowledge)
        XCTAssertEqual(DocumentInspector.section(for: .citations, in: doc), .knowledge)
        XCTAssertEqual(DocumentInspector.section(for: .notes, in: doc), .notes)
        XCTAssertEqual(DocumentInspector.section(for: .annotations, in: doc), .notes)
        XCTAssertEqual(DocumentInspector.section(for: .interpretations, in: doc), .notes)
    }

    func testEditsIsAvailableForImageDocsAndFallsBackToSource() {
        let doc = imageDoc()
        // #3593 reversed #3434: edit controls came back into the Inspector for
        // image/PDF/page docs (Lightroom-style), so a persisted `.edits`
        // selection is no longer clamped away for an image doc.
        XCTAssertEqual(DocumentInspector.clampedSelectedTab(.edits, for: doc), .edits)
        // Edits still isn't mapped to any of the 4 top-level sections, so the
        // section lookup falls back to Source.
        XCTAssertEqual(DocumentInspector.section(for: .edits, in: doc), .source)
    }

    func testKnownFacetSurvivesClamp() {
        let doc = imageDoc()
        XCTAssertEqual(DocumentInspector.clampedSelectedTab(.knowledgeGraph, for: doc), .knowledgeGraph)
    }
}
