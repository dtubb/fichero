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

    func testTheKgFilterIsOneInlineFieldNotAPopoverPerCollapsedTrigger() throws {
        // `panes.chrome.one-filter-pattern`: the Entities/Claims filter is one `PaneFilterField` in the mini toolbar, which
        // every rung of the footer's ladder mounts; there is no popover flag, no condensed button and no overflow row for it.
        for path in ["Views/Library/LibraryView+BottomActionBar.swift", "Views/Library/LibraryView+MiniToolbar.swift"] {
            XCTAssertFalse(try source(path).contains("showingKgFilterPopover"), "\(path) went back to a popover for the filter")
        }
        let bar = try source("Views/Library/LibraryView+MiniToolbar.swift")
        XCTAssertEqual(bar.components(separatedBy: "accessibilityID: \"kgContentFilterField\"").count - 1, 1)
    }
}
