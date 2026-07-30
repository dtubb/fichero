@testable import Fichero
import XCTest

/// #4355 — one highlight-layer model with a precedence keyed on the visible
/// split, instead of each feature drawing independently.
final class ReaderHighlightLayersTests: XCTestCase {

    // MARK: - Precedence per split

    func testSideBySideFindLeadsInTheTranscriptAndMirrorsOntoTheImage() {
        let split = ReaderVisibleSplit(
            showsPageImage: true,
            showsTranscript: true,
            isFinding: true
        )
        XCTAssertEqual(ReaderHighlightPrecedence.leadingLayer(for: split), .findMatch)
        XCTAssertTrue(
            ReaderHighlightPrecedence.isVisible(.geometryBox, in: split),
            "the match's box lights up on the image — the payoff of #4309's geometry"
        )
        XCTAssertTrue(ReaderHighlightPrecedence.mirrorsAcrossPanes(split))
    }

    func testImageOnlyLetsGeometryCarryTheMeaning() {
        let split = ReaderVisibleSplit(showsPageImage: true)
        XCTAssertEqual(ReaderHighlightPrecedence.leadingLayer(for: split), .geometryBox)
        XCTAssertFalse(ReaderHighlightPrecedence.isVisible(.currentPage, in: split))
        XCTAssertFalse(ReaderHighlightPrecedence.mirrorsAcrossPanes(split))
    }

    func testKnowledgePaneLetsEntityClaimLead() {
        let split = ReaderVisibleSplit(showsTranscript: true, showsKnowledge: true)
        XCTAssertEqual(ReaderHighlightPrecedence.leadingLayer(for: split), .entityClaim)
    }

    func testFindOutranksKnowledgeWhileActive() {
        let split = ReaderVisibleSplit(
            showsTranscript: true,
            showsKnowledge: true,
            isFinding: true
        )
        XCTAssertEqual(ReaderHighlightPrecedence.leadingLayer(for: split), .findMatch)
        XCTAssertFalse(
            ReaderHighlightPrecedence.isVisible(.entityClaim, in: split),
            "the same surface must not tint for knowledge while it is highlighting matches"
        )
    }

    func testSelectionAlwaysLeads() {
        let split = ReaderVisibleSplit(
            showsPageImage: true,
            showsTranscript: true,
            isFinding: true,
            hasSelection: true
        )
        XCTAssertEqual(ReaderHighlightPrecedence.leadingLayer(for: split), .selection)
    }

    // MARK: - The current-page layer (#4356)

    func testCurrentPageDrawsWheneverATranscriptIsVisible() {
        for split in [
            ReaderVisibleSplit(showsTranscript: true),
            ReaderVisibleSplit(showsPageImage: true, showsTranscript: true, isFinding: true),
            ReaderVisibleSplit(showsTranscript: true, showsKnowledge: true)
        ] {
            XCTAssertTrue(
                ReaderHighlightPrecedence.isVisible(.currentPage, in: split),
                "the previewed page stays marked — it is a page marker, not a text mark"
            )
        }
    }

    func testCurrentPageNeverLeads() {
        let split = ReaderVisibleSplit(showsPageImage: true, showsTranscript: true)
        let layers = ReaderHighlightPrecedence.layers(for: split)
        XCTAssertEqual(layers.first, .currentPage, "drawn behind everything else")
        XCTAssertNotEqual(layers.last, .currentPage)
    }

    // MARK: - Nothing visible, nothing highlighted

    func testEmptySplitHighlightsNothing() {
        XCTAssertTrue(ReaderHighlightPrecedence.layers(for: ReaderVisibleSplit()).isEmpty)
        XCTAssertNil(ReaderHighlightPrecedence.leadingLayer(for: ReaderVisibleSplit()))
    }

    // MARK: - Distinct visual language

    func testEveryLayerHasItsOwnTreatment() {
        let treatments = ReaderHighlightLayer.allCases.map(\.treatment.rawValue)
        XCTAssertEqual(
            Set(treatments).count,
            ReaderHighlightLayer.allCases.count,
            "two visible layers must stay distinguishable"
        )
        XCTAssertEqual(
            ReaderHighlightLayer.findMatch.treatment,
            .findYellow,
            "find yellow is reserved for find matches"
        )
    }
}
