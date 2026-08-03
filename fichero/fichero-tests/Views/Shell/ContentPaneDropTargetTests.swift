import XCTest

@testable import Fichero

/// The content-pane external drop (#4184), and why the #4458 AppKit bridge that
/// preceded it could never have worked.
///
/// The bridge, `ContentDropTargetView`, was merged with tests — and those tests
/// pinned the two properties that made it non-functional:
///
///   1. `hitTest(_:)` always returns nil. That was argued as safety ("this view
///      structurally cannot intercept a click") and the test EXERCISED it. But
///      AppKit's drag-destination search walks `hitTest` too, so a view that
///      answers "not me" is never found as a destination either.
///   2. `performDragOperation` read providers via
///      `NSPasteboard.readObjects(forClasses: [NSItemProvider.self])`.
///      `readObjects(forClasses:)` requires every class to conform to
///      `NSPasteboardReading`, and `NSItemProvider` does not — it is
///      `NSSecureCoding`/`NSCopying`. So that call could never return providers,
///      and the test written for it only asserted the SOURCE ORDER of a
///      `guard` above the callback.
///
/// Both are provable from the API contract. Neither needed the live drag the
/// authoring lane said was required, and a full test file passed against code
/// that could not deliver a single drop. That is the failure this file exists to
/// avoid repeating: assert what the drop path must DO, not what its source says.
final class ContentPaneDropTargetTests: XCTestCase {

    private static func appSource(_ relativePath: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()   // Shell
            .deletingLastPathComponent()   // Views
            .deletingLastPathComponent()   // fichero-tests
            .deletingLastPathComponent()   // fichero
            .appendingPathComponent("fichero")
            .appendingPathComponent(relativePath)
        let source = try String(contentsOf: url, encoding: .utf8)
        // An unreadable or empty file must fail loudly rather than let every
        // `contains` below pass vacuously.
        XCTAssertFalse(source.isEmpty, "\(relativePath) is empty — this guard measures nothing")
        return source
    }

    private static func detailColumnBody() throws -> String {
        try appSource("Views/Shell/ContentView/Layout/ContentView+RootLayout.swift")
            .components(separatedBy: "private var detailColumn: some View {")[1]
            .components(separatedBy: "\n    }")[0]
    }

    /// The drop path must exist AND be fed. #4408's "wired but unfed" shape:
    /// a destination that exists but never reaches the handler protects nothing.
    func testContentPaneDropIsMountedOnTheDetailColumnAndCallsTheHandler() throws {
        let body = try Self.detailColumnBody()
        // `.onDrop(of: [.item]` unclosed: `isTargeted:` is load-bearing —
        // without it Swift resolves to `.onDrop(of:delegate:)` and rejects the
        // closure — so requiring the immediate `)` forbade the only spelling
        // that compiles.
        XCTAssertTrue(body.contains(".onDrop(of: [.item]"))
        XCTAssertTrue(body.contains("handleContentPaneExternalDrop(providers)"))
    }

    /// #4184's actual finding: a `.fileURL`-only destination silently discarded
    /// drags from Mail, Safari and in-progress downloads, which advertise a
    /// content UTI and no file promise. `.item` is UTType's root, so narrowing
    /// this back to `.fileURL` reintroduces exactly that silent loss.
    func testContentPaneDropAcceptsTheItemRootNotOnlyFileURLs() throws {
        let body = try Self.detailColumnBody()
        XCTAssertFalse(
            body.contains(".onDrop(of: [.fileURL])"),
            "a fileURL-only content-pane drop silently discards Mail/Safari drags (#4184)"
        )
    }

    /// The one reason #4184's original `.onDrop` was reverted was SCOPE — it
    /// was applied to the whole `NavigationSplitView`, so it could not be ruled
    /// out as a hit-testing risk for nested sidebar rows. It belongs on the
    /// detail column, where the sidebar is not inside the modified view at all.
    func testTheDropIsScopedToTheDetailColumnNotTheWholeSplitView() throws {
        let source = try Self.appSource("Views/Shell/ContentView/Layout/ContentView+RootLayout.swift")
        let outsideDetailColumn = source
            .components(separatedBy: "private var detailColumn: some View {")[0]
        XCTAssertFalse(
            outsideDetailColumn.contains(".onDrop(of: [.item])"),
            "the content-pane drop must not be applied above the detail column (#4184's revert reason)"
        )
    }

    /// The dead bridge must stay dead. Reinstating a view whose `hitTest`
    /// returns nil puts back a drop target AppKit's destination search cannot
    /// find — and it read as "safe by construction" convincingly enough to ship
    /// once already.
    func testTheHitTestNilAppKitBridgeIsGone() throws {
        let layout = try Self.appSource("Views/Shell/ContentView/Layout/ContentView+RootLayout.swift")
        XCTAssertFalse(layout.contains("ContentDropTargetView {"))

        let bridge = try AppSource.root()
            .appendingPathComponent("Views/Shell/ContentView/ContentDropTargetView.swift")
        XCTAssertFalse(
            FileManager.default.fileExists(atPath: bridge.path),
            "ContentDropTargetView is back; see this file's header for why it cannot receive drops"
        )
    }

    /// One loader for every external drop. The sidebar row path and this one
    /// must not diverge into two fallback chains — that divergence is how one
    /// surface accepted a Safari drag and another dropped it.
    func testHandlerReusesTheSharedExternalFileDropLoader() throws {
        let handlerBody = try Self.appSource("Views/Shell/ContentView/Actions/ContentView+ActionsImport.swift")
            .components(separatedBy: "func handleContentPaneExternalDrop(")[1]
            .components(separatedBy: "\n    func handleFileDrop")[0]
        XCTAssertTrue(handlerBody.contains("ExternalFileDropLoader.loadAnyFileURL(from: provider)"))
    }

    /// A drop the OS was told we accepted must never end in silence. The
    /// synchronous `true` is a promise; "all loads failed" has to be said.
    func testAllLoadsFailingReportsInsteadOfVanishing() throws {
        let handlerBody = try Self.appSource("Views/Shell/ContentView/Actions/ContentView+ActionsImport.swift")
            .components(separatedBy: "func handleContentPaneExternalDrop(")[1]
            .components(separatedBy: "\n    func handleFileDrop")[0]
        XCTAssertTrue(handlerBody.contains("guard !urls.isEmpty else"))
        XCTAssertTrue(handlerBody.contains("Couldn't read the dropped item(s). Nothing was imported."))
    }
}
