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
}
