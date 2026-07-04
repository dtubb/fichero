@testable import Fichero
import SwiftUI
import XCTest

/// The `AppViewMode` save contract that scene-lifecycle persistence flushes —
/// macOS on `willTerminate`, iOS on `scenePhase == .background` (#3016). Restore
/// keys off the serialized `type`, so the type mapping must stay exhaustive and
/// stable across every mode or a terminated session reopens on the wrong view.
final class ContentViewPersistenceTests: XCTestCase {
    func testSerializeViewModeTypeMappingIsStableForEveryMode() {
        let cases: [(AppViewMode, String)] = [
            (.library(nil), "library"),
            (.search(nil), "search"),
            (.chat(nil), "chat"),
            (.comparison(nil), "comparison"),
            (.workflow(nil), "workflow"),
            (.chain(nil), "chain"),
            (.batches, "activity"),
            (.batch(nil), "activity"),
            (.automation, "automation"),
            (.schedule(nil), "schedule"),
            (.trigger(nil), "trigger"),
            (.activity(nil), "activity")
        ]
        for (mode, expectedType) in cases {
            let result = ContentView.serializeViewMode(mode)
            XCTAssertEqual(result.type, expectedType, "\(mode)")
            XCTAssertNil(result.id, "nil-selection \(mode) must serialize a nil id")
        }
    }

    /// Column-visibility persistence must round-trip so a restored window keeps
    /// its sidebar state after termination.
    func testColumnVisibilityRawRoundTrips() {
        for visibility in [NavigationSplitViewVisibility.automatic, .detailOnly, .doubleColumn] {
            let raw = ContentView.persistedColumnVisibilityRaw(for: visibility)
            XCTAssertEqual(ContentView.restoredColumnVisibility(from: raw), visibility, "\(visibility)")
        }
    }

    // MARK: - Sidebar-selection restore adapter (#3036)
    // @SceneStorage is now a restore-once/write-through persistence adapter feeding
    // the single source (SidebarSelectionState). This maps stored (type, itemId)
    // to the prefixed sidebar id used to restore that source.

    func testSidebarSelectionIdMapsPersistedTypeToPrefixedId() {
        XCTAssertEqual(ContentView.sidebarSelectionId(for: "library", itemId: "abc"), "doc:abc")
        XCTAssertEqual(ContentView.sidebarSelectionId(for: "search", itemId: "s1"), "search:s1")
        XCTAssertEqual(ContentView.sidebarSelectionId(for: "chat", itemId: "c1"), "chat:c1")
        XCTAssertEqual(ContentView.sidebarSelectionId(for: "workflow", itemId: "wf"), "workflow:wf")
        XCTAssertEqual(ContentView.sidebarSelectionId(for: "activity", itemId: "run"), "activity:run")
    }

    /// Already-prefixed ids are idempotent (restore-then-click must not double-prefix).
    func testSidebarSelectionIdIsIdempotentOnPrefixedIds() {
        XCTAssertEqual(ContentView.sidebarSelectionId(for: "library", itemId: "doc:abc"), "doc:abc")
        XCTAssertEqual(ContentView.sidebarSelectionId(for: "workflow", itemId: "workflow:wf"), "workflow:wf")
    }

    func testSidebarSelectionIdNilForEmptyOrMissingItem() {
        XCTAssertNil(ContentView.sidebarSelectionId(for: "library", itemId: nil))
        XCTAssertNil(ContentView.sidebarSelectionId(for: "library", itemId: ""))
    }

    /// Restore-to-deleted: the adapter maps the id regardless of whether the item
    /// still exists — existence isn't checked here, so a stale/deleted selection
    /// restores to a prefixed id the List simply shows as no active row.
    func testSidebarSelectionIdMapsEvenIfItemDeleted() {
        XCTAssertEqual(ContentView.sidebarSelectionId(for: "library", itemId: "deleted-id"), "doc:deleted-id")
    }

    /// Unknown types pass through unchanged (defensive default).
    func testSidebarSelectionIdUnknownTypePassesThrough() {
        XCTAssertEqual(ContentView.sidebarSelectionId(for: "mystery", itemId: "x"), "x")
    }
}
