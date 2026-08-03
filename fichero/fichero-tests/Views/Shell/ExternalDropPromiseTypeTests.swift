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
/// The root content-pane drop target keeps `.dropDestination(for: URL.self)`
/// (NOT the robust loader) — DELIBERATELY. `.onDrop(of:)` was tried, but a
/// review found `DropTargetModifiers` attaches where
/// `decoratedNavigationSplitColumn` mounts it, wrapping the WHOLE
/// `NavigationSplitView` (sidebar column included, not just the content
/// pane) — `.onDrop` at that scope risks stealing hit-testing from every
/// nested sidebar row. Nobody could click-test a live build to rule that
/// out, so the swap was reverted. The sidebar row's OWN `.onDrop` (a single
/// leaf view, not a container wrapping other clickable rows) is a
/// different, already-safe case and is UNCHANGED — that's what these
/// tests lock.
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

    func testContentPaneDropStaysOnTransferableForHitTestingSafety() throws {
        let source = try Self.appSource("Views/Shell/ContentView/ContentViewModifiers.swift")
        // .onDrop at this container scope was tried and reverted — see the
        // comment on DropTargetModifiers for why. Locks the revert so a
        // future edit doesn't silently reintroduce the risk without the
        // live click-test that would justify it.
        XCTAssertTrue(source.contains(".dropDestination(for: URL.self)"))
        XCTAssertFalse(source.contains(".onDrop(of: [.item]"))
        // The reasoning must stay attached to the code, not just this test.
        XCTAssertTrue(source.contains("hit-testing from every"))
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
