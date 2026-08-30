@testable import Fichero
import UniformTypeIdentifiers
import XCTest

/// #4530 — the New Library… panel seam.
///
/// Two callers can now start a library create: the in-window path
/// (`LibraryWindow.handleNewLibrary`) and the app-scoped File-menu fallback for
/// when no window is key. They share `NewLibraryPanel` so the panel
/// configuration and the on-disk naming decision cannot drift apart; these
/// tests pin the part that decides what actually lands on disk.
@MainActor
final class NewLibraryPanelTests: XCTestCase {

    // MARK: - Naming (the part that can be wrong on disk)

    func testMissingExtensionIsAdded() {
        let resolved = NewLibraryPanel.resolvedLibraryURL(for: URL(fileURLWithPath: "/tmp/Fieldwork"))
        XCTAssertEqual(resolved.lastPathComponent, "Fieldwork.fichero")
    }

    /// Idempotent: a name the user already typed with the extension must not
    /// become "Fieldwork.fichero.fichero".
    func testExistingExtensionIsNotDuplicated() {
        let resolved = NewLibraryPanel.resolvedLibraryURL(for: URL(fileURLWithPath: "/tmp/Fieldwork.fichero"))
        XCTAssertEqual(resolved.lastPathComponent, "Fieldwork.fichero")
        XCTAssertFalse(resolved.path.contains(".fichero.fichero"))
    }

    /// Case is not significance: `.FICHERO` is the same package type, and
    /// appending again would create a second extension.
    func testExtensionMatchIsCaseInsensitive() {
        let resolved = NewLibraryPanel.resolvedLibraryURL(for: URL(fileURLWithPath: "/tmp/Fieldwork.FICHERO"))
        XCTAssertEqual(resolved.lastPathComponent, "Fieldwork.FICHERO")
    }

    /// #3076: the package NAME is NFC-normalized so a decomposed "ó" from the
    /// panel never becomes a mojibake-variant path.
    func testPackageNameIsNFCNormalized() {
        let decomposed = "Choco\u{0301}"                       // NFD
        let composed = "Chocó".precomposedStringWithCanonicalMapping  // NFC
        // Scalar-level comparison is load-bearing: Swift's String == uses
        // CANONICAL equivalence, so NFD and NFC forms always compare equal —
        // the original `XCTAssertNotEqual(decomposed, composed)` could never
        // pass and this test was born failing in the era the target didn't
        // compile (Aug 4-9). The byte contract lives at the STRING boundary:
        XCTAssertNotEqual(
            Array(decomposed.unicodeScalars), Array(composed.unicodeScalars),
            "fixture is not actually decomposed"
        )
        XCTAssertEqual(
            Array(decomposed.nfcNormalized.unicodeScalars),
            Array(composed.unicodeScalars),
            "String.nfcNormalized must produce byte-for-byte NFC (#3076)"
        )

        // PLATFORM TRUTH, measured: EVERY Foundation URL init re-decomposes
        // path components (fileURLWithPath, filePath:, appendingPathComponent
        // all hand back NFD), so byte-NFC cannot be pinned through a URL.
        // What the URL layer CAN promise is the canonical name+extension; the
        // wire re-normalizes the string where it actually leaves the app
        // (LibraryPathMiddleware.nfcNormalized, backend #3071).
        let resolved = NewLibraryPanel.resolvedLibraryURL(
            for: URL(fileURLWithPath: "/tmp/\(decomposed)")
        )
        XCTAssertEqual(resolved.lastPathComponent, "\(composed).fichero")
    }

    /// Side effect that must NOT happen: normalization is scoped to the leaf.
    /// The parent directory already exists on disk under whatever form the
    /// filesystem gave it, so rewriting it would point the save at a path that
    /// does not exist.
    func testParentDirectoryIsLeftUntouched() {
        let decomposedParent = "Campo\u{0301}"
        let resolved = NewLibraryPanel.resolvedLibraryURL(
            for: URL(fileURLWithPath: "/tmp/\(decomposedParent)/Notes")
        )
        XCTAssertTrue(
            resolved.deletingLastPathComponent().path.hasSuffix(decomposedParent),
            "the user-chosen parent directory must be preserved byte-for-byte"
        )
        XCTAssertEqual(resolved.lastPathComponent, "Notes.fichero")
    }

    // MARK: - Panel configuration

    /// The panel must offer the app's OWN library type, not the abstract
    /// `.package` it used to use — `.package` also matches `.app`, `.rtfd` and
    /// every other bundle, and carries no extension for the panel to apply.
    func testLibraryUTTypeResolvesFromTheInfoPlistDeclaration() throws {
        let type = try XCTUnwrap(
            UTType.ficheroLibrary,
            "app.fichero.fichero.library is not declared — the panel would fall back to no type filter"
        )
        XCTAssertTrue(type.conforms(to: .package), "the library type must still be a package")
        XCTAssertEqual(type.preferredFilenameExtension, "fichero")
    }

    /// The create panel opens somewhere the ENGINE will serve. The engine
    /// refuses any library outside `ingest_allowed_roots()` with a 403 that the
    /// app reports only as "Library load failed", so a default of "wherever the
    /// panel last was" produces libraries that are created successfully and
    /// then never work. `~/Documents` is on the allowed list.
    func testDefaultDirectoryIsAnEngineServableLocation() throws {
        let directory = try XCTUnwrap(
            NewLibraryPanel.defaultLibraryDirectory,
            "no default create location — the panel would open on an arbitrary path (#4530)"
        )
        let documents = try XCTUnwrap(
            FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first
        )
        XCTAssertEqual(directory.standardizedFileURL, documents.standardizedFileURL)
    }

    // MARK: - Both callers share the seam

    /// #4493: routed through the shared `AppSource` walk instead of
    /// counting `deletingLastPathComponent()` calls. Counting is correct
    /// only for this file's CURRENT depth — move the file and it resolves
    /// somewhere else and fails later as an unrelated file-not-found.
    private static func appSource(_ relativePath: String) throws -> String {
        let source = try AppSource.text(relativePath)
        XCTAssertFalse(source.isEmpty, "\(relativePath) is empty — this guard measures nothing")
        return source
    }

    /// Neither caller may re-implement the panel or the naming rule: a second
    /// copy is how the two create paths would start producing different files.
    func testBothCreatePathsGoThroughTheSharedSeam() throws {
        for path in ["App/LibraryWindow+Actions.swift", "App/Menus/FileMenuCommands.swift"] {
            let source = try Self.appSource(path)
            XCTAssertTrue(
                source.contains("NewLibraryPanel.makeSavePanel()"),
                "\(path) builds its own save panel instead of sharing the seam (#4530)"
            )
            XCTAssertTrue(
                source.contains("NewLibraryPanel.resolvedLibraryURL(for:"),
                "\(path) re-implements the extension/NFC naming rule (#4530)"
            )
        }
    }

    /// A failed create must reach the user. It was log-only, so pressing
    /// Create could produce no library and no reason — the silent-failure
    /// shape rule zero forbids.
    func testBothCreatePathsSurfaceFailureToTheUser() throws {
        for path in ["App/LibraryWindow+Actions.swift", "App/Menus/FileMenuCommands.swift"] {
            let source = try Self.appSource(path)
            XCTAssertTrue(
                source.contains("NewLibraryPanel.presentCreateFailure("),
                "\(path) swallows a create failure into the log (#4530)"
            )
        }
    }

    /// #4062 must survive this refactor: New Library… still creates in place in
    /// the window that ran it, and does not open a window.
    func testInWindowCreateStillDoesNotOpenAWindow() throws {
        let source = try Self.appSource("App/LibraryWindow+Actions.swift")
        let start = try XCTUnwrap(source.range(of: "func handleNewLibrary() {"))
        let end = try XCTUnwrap(
            source.range(of: "func handleSaveLibrary() {", range: start.lowerBound..<source.endIndex)
        )
        let body = String(source[start.lowerBound..<end.lowerBound])

        XCTAssertTrue(body.contains("assignLibrary(id: newLibrary.id)"))
        XCTAssertFalse(body.contains("openWindow(id:"))
    }
}
