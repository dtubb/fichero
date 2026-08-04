@testable import Fichero
import XCTest

/// Source-surface tests for #4184 — "drag-and-drop of a PDF doesn't work
/// from some locations". Root cause: SwiftUI's `Transferable`-based
/// `.dropDestination(for: URL.self)` decodes a URL via the SAME
/// `public.file-url` promise `loadObject(URL.self)` uses. Finder drags
/// supply that promise; Mail attachment drags, Safari image/PDF drags, and
/// in-progress Downloads items often advertise only a content UTI
/// (`public.jpeg`, `com.adobe.pdf`) with no file-url promise — and are
/// silently missed. `ExternalFileDropLoader` (extracted from the sidebar
/// row drop target's #587 fix) falls back to
/// `loadFileRepresentation(forTypeIdentifier:)` against the provider's own
/// advertised UTI, which reads them.
///
/// `DropTargetModifiers` now carries NO drop target at all (#4458). It attaches
/// where `decoratedNavigationSplitColumn` mounts it, wrapping the WHOLE
/// `NavigationSplitView` — sidebar column included — and every target ever put
/// there shadowed the scoped ones beneath it. The content-pane drop lives on
/// `detailColumn`, which `ContentPaneDropTargetTests` locks.
///
/// This test used to assert the opposite of `DroppedURLClassificationTests`'
/// guard on the same file: one demanded `.dropDestination(for: URL.self)` be
/// PRESENT, the other demanded it be ABSENT. Both were in the suite at once,
/// so at least one had been failing since `6a11a9fc2` — which is its own
/// finding about reading a suite's result rather than its intent.
///
/// The sidebar row's OWN `.onDrop` (a single leaf view, not a container
/// wrapping other clickable rows) is a different, already-safe case and is
/// UNCHANGED in scope — that's what these tests lock.
final class ExternalDropPromiseTypeTests: XCTestCase {
    private static func appSource(_ relativePath: String) throws -> String {
        let url = try AppSource.root()
            .appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }

    func testExternalFileDropLoaderFallsBackToFileRepresentation() throws {
        let source = try Self.appSource("Services/ExternalFileDropLoader.swift")
        // The cheap path a Finder drag satisfies.
        XCTAssertTrue(source.contains("canLoadObject(ofClass: URL.self)"))
        // The fallback a content-UTI-only provider (Mail/Safari/Downloads)
        // actually needs.
        XCTAssertTrue(source.contains("loadFileRepresentation(forTypeIdentifier:"))
        XCTAssertTrue(source.contains("for identifier in utis"))
    }

    /// The window-wide modifier must carry NO drop target, in EITHER spelling.
    ///
    /// Naming just one is how this regressed: the reverted `.onDrop` was named
    /// in a 40-line comment while nothing enforced its absence, and
    /// `6a11a9fc2` put it straight back.
    func testTheWindowWideModifierCarriesNoDropTargetAtAll() throws {
        let source = try Self.appSource("Views/Shell/ContentView/ContentViewModifiers.swift")
        let code = source
            .split(separator: "\n", omittingEmptySubsequences: false)
            .filter { !$0.trimmingCharacters(in: .whitespaces).hasPrefix("//") }
            .filter { !$0.trimmingCharacters(in: .whitespaces).hasPrefix("///") }
            .joined(separator: "\n")
        XCTAssertFalse(
            code.contains(".onDrop("),
            "an .onDrop here sits above every sidebar row and folder cell (#4458)"
        )
        XCTAssertFalse(
            code.contains(".dropDestination("),
            "a Transferable target here is the #4401 hollow-copy path (#4458)"
        )
        // The reasoning must stay attached to the code, not just this test.
        XCTAssertTrue(source.contains("hit-testing"))
        XCTAssertTrue(source.contains("Do not re-add a drop target"))
    }

    func testSidebarRowDropDelegatesToTheSameSharedLoader() throws {
        // Locks the dedup: the sidebar row's own #587 fix now calls the
        // shared implementation instead of keeping a private copy that
        // could drift. The row's `.onDrop` itself is unchanged — still a
        // single leaf view's own drop target, the safe case.
        let source = try Self.appSource("Views/Sidebar/ItemRow/SidebarItemRow+DropHandlers.swift")
        XCTAssertTrue(source.contains("try await ExternalFileDropLoader.loadAnyFileURL(from: provider)"))
        XCTAssertFalse(source.contains("private static func loadFileRepresentation"))
    }
}
