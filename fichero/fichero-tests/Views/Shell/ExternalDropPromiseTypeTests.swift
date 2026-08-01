@testable import Fichero
import XCTest

/// Source-surface tests for #4184 — "drag-and-drop of a PDF doesn't work
/// from some locations". Root cause: the root content-pane drop target used
/// SwiftUI's `Transferable`-based `.dropDestination(for: URL.self)`, which
/// decodes a URL via the SAME `public.file-url` promise `loadObject(URL.self)`
/// uses. Finder drags supply that promise; Mail attachment drags, Safari
/// image/PDF drags, and in-progress Downloads items often advertise only a
/// content UTI (`public.jpeg`, `com.adobe.pdf`) with no file-url promise —
/// `Transferable` silently drops those. `ExternalFileDropLoader` (extracted
/// from the sidebar row drop target's #587 fix) falls back to
/// `loadFileRepresentation(forTypeIdentifier:)` against the provider's own
/// advertised UTI, which reads them. This was a promise-type problem, not a
/// drop-target problem — exactly as the issue predicted.
final class ExternalDropPromiseTypeTests: XCTestCase {
    private static func appSource(_ relativePath: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero")
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

    func testContentPaneDropUsesTheSharedLoaderNotTransferable() throws {
        let source = try Self.appSource("Views/Shell/ContentView/ContentViewModifiers.swift")
        // The weak Transferable path is gone from the root drop target.
        XCTAssertFalse(source.contains(".dropDestination(for: URL.self)"))
        // Replaced with the NSItemProvider path sharing the sidebar's fix.
        XCTAssertTrue(source.contains(".onDrop(of: [.item], isTargeted: $isDropTargeted)"))
        XCTAssertTrue(source.contains("ExternalFileDropLoader.loadAnyFileURL(from: provider)"))
    }

    func testSidebarRowDropDelegatesToTheSameSharedLoader() throws {
        // Locks the dedup: the sidebar row's own #587 fix now calls the
        // shared implementation instead of keeping a private copy that
        // could drift from the content-pane's (#4184's root cause pattern —
        // "three implementations of one action" — one step closer to zero).
        let source = try Self.appSource("Views/Sidebar/ItemRow/SidebarItemRow+DropHandlers.swift")
        XCTAssertTrue(source.contains("try await ExternalFileDropLoader.loadAnyFileURL(from: provider)"))
        XCTAssertFalse(source.contains("private static func loadFileRepresentation"))
    }
}
