@testable import Fichero
import XCTest

/// #4966: split out of `LibraryHeaderFooterCollapseAgreementTests` (#5052). What remains here are
/// the ABSENCE and COUNT claims about the shared footer's collapse ladder; whether it really
/// collapses at a given width is a mounted-view question and stays in that class.
final class KGFooterCollapseGuardrailTests: XCTestCase {

    private func source(_ relativePath: String) throws -> String {
        try AppSource.code(relativePath)
    }

    func testKgFilterIsNotInTheAlwaysInlineEssentialTier() throws {
        let source = try source("Views/Library/LibraryView+BottomActionBar.swift")
        // The tier must be FOUND: a renamed property would otherwise pass this vacuously.
        let tier = try XCTUnwrap(
            AppSource.codeOnly(source).components(separatedBy: "private var essentialBarButtons: some View {").dropFirst().first,
            "essentialBarButtons not found — update this guardrail with the rename"
        )
        let body = try XCTUnwrap(tier.components(separatedBy: "\n    }").first)
        XCTAssertFalse(
            body.contains("kgContentFilterControls"),
            "the filter must not be in the always-inline essential tier any more"
        )
    }

    func testTheSameShowingKgFilterPopoverStateBacksBothCollapsedTriggers() throws {
        let source = try source("Views/Library/LibraryView+BottomActionBar.swift")
        // Both the condensed button and the overflow-menu row must set the SAME popover flag, and
        // the popover itself must be attached once, at the bar's own outer container — not on
        // either trigger individually, which would vanish along with whichever rung isn't
        // currently rendered.
        XCTAssertEqual(
            source.components(separatedBy: "showingKgFilterPopover = true").count - 1, 2,
            "exactly two triggers (condensed button, overflow row) should open the popover"
        )
        XCTAssertEqual(
            source.components(separatedBy: ".popover(isPresented: $showingKgFilterPopover)").count - 1, 1,
            "the popover itself must be presented exactly once, not per-trigger"
        )
    }
}
