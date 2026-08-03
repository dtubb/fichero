@testable import Fichero
import Foundation
import Testing

// `FolderAccessManager.requestFolderAccess` — the NSOpenPanel that asks the user
// to grant access to a library folder — existed, was correct, and had ZERO
// callers (#4217). A library whose folder is unreadable therefore opened and
// then silently failed to read anything: no prompt, no error, no log the user
// could act on.
//
// Nothing catches that shape. Coverage says nothing about a function nobody
// calls, the compiler says nothing, and reading the function tells you it works.
// This asserts the call site exists.
//
// WHAT THIS DOES NOT PROVE: that the prompt is REACHABLE. A future edit could
// wrap the call in a condition that is never true, or strand it in a dead
// branch, and this test would stay green. It catches DELETION, which is the
// realistic regression, and nothing more. Proving the prompt fires needs a
// sandboxed build and a library whose folder is genuinely unreadable — neither
// is available in this suite.
@Suite("Library open prompts for access instead of failing silently (#4217)")
struct LibraryAccessPromptWiringTests {

    private func appSource(_ relativePath: String) throws -> String {
        let url = try AppSource.root()
            .appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }

    @Test("the library-open path calls requestFolderAccess")
    func openLibraryPromptsForAccess() throws {
        let source = try appSource("Models/LibraryManager+Operations.swift")
        #expect(
            source.contains("requestFolderAccess("),
            "opening a library whose folder is unreadable must prompt, not proceed silently"
        )
    }

    // The guard is the whole point: prompting on every open would be worse than
    // the silence. It must fire only when access is actually missing.
    @Test("the prompt is gated on access actually being unavailable")
    func promptIsGatedOnMissingAccess() throws {
        let source = try appSource("Models/LibraryManager+Operations.swift")
        #expect(source.contains("hasAccess(to:"), "must check access before prompting")
    }

    // A temporary library lives in the app's own container and needs no grant;
    // prompting for one would be a spurious panel on a path we already own.
    @Test("temporary libraries are excluded from the prompt")
    func temporaryLibrariesAreExcluded() throws {
        let source = try appSource("Models/LibraryManager+Operations.swift")
        #expect(source.contains("needsSecurityAccess"))
    }

    // The panel exists on macOS only; the iOS stub is a no-op by design, so the
    // call site must not compile into the iOS build.
    @Test("the prompt is macOS-only")
    func promptIsMacOnly() throws {
        let source = try appSource("Models/LibraryManager+Operations.swift")
        let promptRange = try #require(source.range(of: "requestFolderAccess("))
        let before = source[source.startIndex..<promptRange.lowerBound]
        #expect(
            before.contains("#if os(macOS)"),
            "the call must sit inside a macOS conditional — the iOS stub only logs"
        )
    }
}
