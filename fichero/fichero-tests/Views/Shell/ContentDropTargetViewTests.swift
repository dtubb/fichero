#if canImport(AppKit)
import AppKit
import XCTest

@testable import Fichero

/// #4458 — the content-pane external-drop bridge, provably safe by
/// construction rather than inferred from a hierarchy read.
///
/// `.onDrop(of:)` at the whole-`NavigationSplitView` scope was reverted
/// during #4184 because nobody could prove from the hierarchy alone that it
/// wouldn't steal hit-testing from nested sidebar rows. `ContentDropTargetView`
/// answers that differently: `hitTest(_:)` always returns nil, which is a
/// property this test EXERCISES directly — actually instantiating the view
/// and calling `hitTest`, not just reading source for the override's
/// presence — because a real behavioral check is the whole argument for
/// building this instead of scoping the risky version to `detailColumn`.
final class ContentDropTargetViewTests: XCTestCase {
    /// The load-bearing guarantee: this view can never become a click/tap
    /// target, regardless of where it sits in the hierarchy. If a future
    /// edit removes or weakens the override, this fails immediately instead
    /// of surfacing as "clicking library items stopped working" days later.
    func testHitTestAlwaysReturnsNilRegardlessOfPoint() {
        let view = ContentDropCaptureView(frame: NSRect(x: 0, y: 0, width: 400, height: 400))

        for point in [
            NSPoint(x: 0, y: 0),
            NSPoint(x: 200, y: 200),
            NSPoint(x: 399, y: 399),
            NSPoint(x: -50, y: -50),   // outside the frame entirely
            NSPoint(x: 1000, y: 1000)  // wildly outside
        ] {
            XCTAssertNil(
                view.hitTest(point),
                "hitTest(\(point)) must be nil — this view must never intercept a click"
            )
        }
    }

    /// A real `NSDraggingInfo` needs a live drag session to construct, which
    /// this test target cannot start headlessly, so `performDragOperation`'s
    /// empty-providers guard is locked structurally instead: reads the
    /// pasteboard, guards on non-empty, only THEN fires the callback — the
    /// same shape `handleProvidersDrop`'s own `guard !providers.isEmpty`
    /// guard uses (#4459), so a drop with nothing readable can't silently
    /// report success.
    func testPerformDragOperationGuardsOnNonEmptyBeforeFiringCallback() throws {
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero/Views/Shell/ContentView/ContentDropTargetView.swift")
        let source = try String(contentsOf: url, encoding: .utf8)
        let body = source.components(separatedBy: "func performDragOperation(")[1]
        let guardIndex = body.range(of: "guard !providers.isEmpty else { return false }")
        let callbackIndex = body.range(of: "onProviders?(providers)")
        XCTAssertNotNil(guardIndex)
        XCTAssertNotNil(callbackIndex)
        if let guardIndex, let callbackIndex {
            XCTAssertTrue(guardIndex.lowerBound < callbackIndex.lowerBound)
        }
    }

    // MARK: - Wiring (#4458): the bridge must actually be called, not just exist

    private static func appSource(_ relativePath: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero")
            .appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }

    /// The exact "wired but unfed" shape #4408 caught: a bridge that exists
    /// but nothing in the view tree ever constructs it protects nothing.
    func testContentDropTargetViewIsMountedOnTheDetailColumn() throws {
        let source = try Self.appSource("Views/Shell/ContentView/Layout/ContentView+RootLayout.swift")
        let detailColumnBody = source
            .components(separatedBy: "private var detailColumn: some View {")[1]
            .components(separatedBy: "\n    }")[0]
        XCTAssertTrue(detailColumnBody.contains("ContentDropTargetView {"))
        XCTAssertTrue(detailColumnBody.contains("handleContentPaneExternalDrop(providers)"))
    }

    /// #4184's whole point: the sidebar row's OWN safe leaf-scope `.onDrop`
    /// import path still goes through the shared loader — this bridge is
    /// additive, not a second implementation.
    func testHandlerReusesTheSharedExternalFileDropLoader() throws {
        let source = try Self.appSource("Views/Shell/ContentView/Actions/ContentView+ActionsImport.swift")
        let handlerBody = source
            .components(separatedBy: "func handleContentPaneExternalDrop(")[1]
            .components(separatedBy: "\n    func handleFileDrop")[0]
        XCTAssertTrue(handlerBody.contains("ExternalFileDropLoader.loadAnyFileURL(from: provider)"))
    }

    /// `.background`, not `.overlay` — the z-order argument for why a folder
    /// cell's own `.dropDestination` keeps priority (see this view's own
    /// doc comment) only holds if it's actually placed behind.
    func testBridgeIsPlacedInBackgroundNotOverlay() throws {
        let source = try Self.appSource("Views/Shell/ContentView/Layout/ContentView+RootLayout.swift")
        let detailColumnBody = source
            .components(separatedBy: "private var detailColumn: some View {")[1]
            .components(separatedBy: "\n    }")[0]
        XCTAssertTrue(detailColumnBody.contains(".background {"))
        XCTAssertFalse(detailColumnBody.contains(".overlay {\n                ContentDropTargetView"))
    }
}
#endif
