@testable import Fichero
import XCTest

/// #4518: closing a library left Preview/Reader/Inspector rendering
/// "empty for this document" states for a document belonging to nothing —
/// Preview offered Retry for a missing file, Reader reported no transcript
/// for "this selection", the inspector counted 0 artifacts under a stale
/// workflow chip. One missed teardown: nothing observed
/// `windowState.libraryId` changing, so ContentView's per-document `@State`
/// snapshots survived the close (`LibraryWorkspaceRoot` swaps stores without
/// remounting the tree).
///
/// Source-assertion style (the in-repo convention for view-wiring guards):
/// the teardown is a View mutation, and these locks pin the wiring that a
/// remount-free store swap cannot verify at runtime in a unit target.
final class LibraryCloseTeardownTests: XCTestCase {

    private static func appSource(_ relativePath: String) throws -> String {
        let url = try AppSource.root()
            .appendingPathComponent(relativePath)
        let source = try String(contentsOf: url, encoding: .utf8)
        XCTAssertFalse(source.isEmpty, "\(relativePath) is empty — this guard measures nothing")
        return source
    }

    /// The onChange seam exists: a library change reaches the teardown.
    func testLibraryIdChangeIsObservedAndRoutedToTheTeardown() throws {
        let rootLayout = try Self.appSource(
            "Views/Shell/ContentView/Layout/ContentView+RootLayout.swift"
        )
        XCTAssertTrue(
            rootLayout.contains(".onChange(of: windowState.libraryId)"),
            "#4518 regression: nothing observes the window's library changing, "
                + "so stale per-document snapshots survive a library close"
        )
        XCTAssertTrue(rootLayout.contains("handleLibraryChange()"))
    }

    /// The teardown clears exactly the per-document snapshots and nothing
    /// that would clobber a cross-library sidebar click.
    func testTeardownClearsSnapshotsButNotTheSidebarSelection() throws {
        let stateEvents = try Self.appSource(
            "Views/Shell/ContentView/ContentView+StateEvents.swift"
        )
        guard let handlerRange = stateEvents.range(of: "func handleLibraryChange()") else {
            return XCTFail("handleLibraryChange() missing from ContentView+StateEvents.swift")
        }
        // The handler body runs from its declaration to the next MARK.
        let tail = String(stateEvents[handlerRange.lowerBound...])
        let body = String(tail.prefix(upTo: tail.range(of: "// MARK:")?.lowerBound ?? tail.endIndex))

        XCTAssertTrue(body.contains("detailDocument = nil"))
        XCTAssertTrue(body.contains("browserSelection.removeAll()"))
        XCTAssertTrue(body.contains("clearTransientSearch()"))
        XCTAssertTrue(body.contains("kgFocusState.clear()"))
        // A cross-library click writes libraryId FIRST and its selection
        // second — clearing the selection id in this handler would clobber
        // the very click being handled.
        XCTAssertFalse(
            body.contains("sidebarSelectionState.selectedItemId = nil"),
            "handleLibraryChange must not wipe the sidebar selection id (#4518 scoping)"
        )
    }
}
