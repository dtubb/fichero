@testable import Fichero
import XCTest

/// spec: panes-magnifiers-workspaces — `panes.library.horizontal-and-entities-parity`
/// (the "Entities view takes over, no library; Claims keeps it" fix).
///
/// The preview-pane policy must NOT depend on which library collection is selected.
/// An earlier `isEntityLibrarySelection` special-case in `showsPreviewPane` returned
/// `false` for the Entities collection, so entities alone lost the preview and
/// reflowed to a full-width takeover (`centerContentRouting`'s `!showsPreviewPane`
/// branch), while Claims — never special-cased — kept the two-pane layout. That
/// violated the stable-panes policy (#1452/#4525). The fix removed the branch, so
/// the policy no longer takes a selection-kind input at all — entity/claim/folder
/// parity is now STRUCTURAL, which is what these tests pin.
final class ShowsPreviewPanePolicyTests: XCTestCase {

    /// The Entities and Claims collections both resolve to `.library`; with no
    /// selection-kind branch, both keep the preview identically. Before the fix,
    /// entities returned false here (takeover) and claims true (two-pane).
    func testLibrarySelectionsKeepPreviewRegardlessOfKind() {
        XCTAssertTrue(ContentView.showsPreviewPane(viewMode: .library(nil), layoutMode: .widescreen))
        XCTAssertTrue(ContentView.showsPreviewPane(viewMode: .library(nil), layoutMode: .standard))
    }

    func testNoneLayoutNeverShowsPreview() {
        XCTAssertFalse(ContentView.showsPreviewPane(viewMode: .library(nil), layoutMode: .none))
        XCTAssertFalse(ContentView.showsPreviewPane(viewMode: .chat(nil), layoutMode: .none))
    }

    func testChatKeepsPreview() {
        XCTAssertTrue(ContentView.showsPreviewPane(viewMode: .chat(nil), layoutMode: .widescreen))
    }

    func testNonLibraryNonChatModesHaveNoPreview() {
        XCTAssertFalse(ContentView.showsPreviewPane(viewMode: .comparison(nil), layoutMode: .widescreen))
        XCTAssertFalse(ContentView.showsPreviewPane(viewMode: .automation, layoutMode: .widescreen))
    }
}
