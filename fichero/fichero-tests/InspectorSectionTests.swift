@testable import Fichero
import XCTest

/// InspectorSection — the 10→4 information-architecture contract (#3434). These
/// lock the approved grouping so the DocumentInspector rewire and
/// WorkflowInspector can't silently drop or double-file a facet.
final class InspectorSectionTests: XCTestCase {

    func testFourSectionsInOrder() {
        XCTAssertEqual(
            InspectorSection.allCases,
            [.source, .artifacts, .knowledge, .notes]
        )
    }

    func testEveryFacetExceptEditsMapsToExactlyOneSection() {
        // #3876 folded Info into the Source body's Content/Info/Outline picker,
        // so the standalone `.info` facet no longer owns a section either.
        for tab in InspectorTab.allCases where tab != .edits && tab != .info {
            let owning = InspectorSection.allCases.filter { $0.facets.contains(tab) }
            XCTAssertEqual(
                owning.count, 1,
                "\(tab.rawValue) must belong to exactly one section, found \(owning.map(\.rawValue))"
            )
        }
    }

    func testEditsIsNotAnInspectorSection() {
        // Image edits leave the inspector for the Reader canvas (design doc).
        XCTAssertNil(InspectorSection.section(for: .edits))
        for section in InspectorSection.allCases {
            XCTAssertFalse(section.facets.contains(.edits))
        }
    }

    func testApprovedGrouping() {
        XCTAssertEqual(InspectorSection.source.facets, [.content])
        XCTAssertEqual(InspectorSection.artifacts.facets, [.artifacts])
        // Related joins Knowledge (#4120): see-also is knowledge-derived
        // (shared entities + embedding neighbors).
        XCTAssertEqual(InspectorSection.knowledge.facets, [.entities, .knowledgeGraph, .citations, .related])
        XCTAssertEqual(InspectorSection.notes.facets, [.notes, .annotations, .interpretations])
    }

    func testReverseMappingMatchesFacets() {
        for section in InspectorSection.allCases {
            for facet in section.facets {
                XCTAssertEqual(InspectorSection.section(for: facet), section)
            }
        }
    }

    func testKnowledgeAbsorbsCitations() {
        // Citations are claims (design doc) — they live under Knowledge, not
        // a tab of their own.
        XCTAssertEqual(InspectorSection.section(for: .citations), .knowledge)
    }

    // MARK: - XCUITest a11y hook contract (#3456/#3457)

    func testAccessibilityIdentifierIsStableAndUniquePerSection() {
        // The top-icon-row switcher exposes one stable per-section id that the
        // UX/XCUITest layer targets — locking the format guards those tests.
        XCTAssertEqual(InspectorSection.source.accessibilityIdentifier, "inspectorSection-Source")
        XCTAssertEqual(InspectorSection.artifacts.accessibilityIdentifier, "inspectorSection-Artifacts")
        XCTAssertEqual(InspectorSection.knowledge.accessibilityIdentifier, "inspectorSection-Knowledge")
        XCTAssertEqual(InspectorSection.notes.accessibilityIdentifier, "inspectorSection-Notes")

        let ids = InspectorSection.allCases.map(\.accessibilityIdentifier)
        XCTAssertEqual(Set(ids).count, InspectorSection.allCases.count, "each section needs a unique hook")
    }
}
