@testable import Fichero
import UniformTypeIdentifiers
import XCTest

/// #4530, #5482 — where a new project lands on disk, and how both File-menu routes reach it.
///
/// A project is made by setup's Where it lives (ruled 2026-10-05): Inside Fichero, or a folder
/// the person chooses (`NewProjectStore`). Both File › Set Up New Project… routes, in a window
/// and with no window key, open that one setup; these tests pin the part that decides what
/// actually lands on disk and that neither route grew its own create path again.
@MainActor
final class NewLibraryPanelTests: XCTestCase {

    private func url(name: String, in folder: String) -> URL? {
        let store = NewProjectStore(libraryManager: LibraryManager.shared)
        store.name = name
        store.place = .chosen(URL(fileURLWithPath: folder, isDirectory: true))
        return store.projectURL
    }

    // MARK: - Naming (the part that can be wrong on disk)

    /// The package always carries the `.fichero` extension.
    func testExtensionIsAdded() throws {
        XCTAssertEqual(try XCTUnwrap(url(name: "Fieldwork", in: "/tmp")).lastPathComponent, "Fieldwork.fichero")
    }

    /// A name with a slash or colon would make a folder path, not a name: it is replaced.
    func testNameCannotMakeAPath() throws {
        let made = try XCTUnwrap(url(name: "A/B:C", in: "/tmp"))
        XCTAssertEqual(made.lastPathComponent, "A-B-C.fichero")
        XCTAssertEqual(made.deletingLastPathComponent().path, "/tmp")
    }

    /// #3076: the package NAME is NFC-normalized so a decomposed "ó" never becomes a
    /// mojibake-variant path.
    func testPackageNameIsNFCNormalized() throws {
        let decomposed = "Choco\u{0301}"                       // NFD
        let composed = "Chocó".precomposedStringWithCanonicalMapping  // NFC
        // Scalar-level comparison is load-bearing: Swift's String == uses
        // CANONICAL equivalence, so NFD and NFC forms always compare equal.
        XCTAssertNotEqual(
            Array(decomposed.unicodeScalars), Array(composed.unicodeScalars),
            "fixture is not actually decomposed"
        )
        XCTAssertEqual(
            Array(decomposed.nfcNormalized.unicodeScalars),
            Array(composed.unicodeScalars),
            "String.nfcNormalized must produce byte-for-byte NFC (#3076)"
        )
        // Foundation URLs re-decompose path components, so byte-NFC cannot be pinned through a
        // URL; what the URL layer promises is the canonical name and extension.
        XCTAssertEqual(try XCTUnwrap(url(name: decomposed, in: "/tmp")).lastPathComponent, "\(composed).fichero")
    }

    /// Normalization is scoped to the leaf: the chosen folder already exists on disk under
    /// whatever form the filesystem gave it, so rewriting it would point at a path that does not.
    func testParentDirectoryIsLeftUntouched() throws {
        let decomposedParent = "Campo\u{0301}"
        let made = try XCTUnwrap(url(name: "Notes", in: "/tmp/\(decomposedParent)"))
        XCTAssertTrue(
            made.deletingLastPathComponent().path.hasSuffix(decomposedParent),
            "the chosen folder must be preserved byte-for-byte"
        )
        XCTAssertEqual(made.lastPathComponent, "Notes.fichero")
    }

    /// Open… offers the app's OWN library type, not the abstract `.package`, which also
    /// matches `.app`, `.rtfd` and every other bundle.
    func testLibraryUTTypeResolvesFromTheInfoPlistDeclaration() throws {
        let type = try XCTUnwrap(
            UTType.ficheroLibrary,
            "app.fichero.fichero.library is not declared — the panel would fall back to no type filter"
        )
        XCTAssertTrue(type.conforms(to: .package), "the library type must still be a package")
        XCTAssertEqual(type.preferredFilenameExtension, "fichero")
    }

    // MARK: - Both routes open the one setup

    private static func appSource(_ relativePath: String) throws -> String {
        let source = try AppSource.text(relativePath)
        XCTAssertFalse(source.isEmpty, "\(relativePath) is empty — this guard measures nothing")
        return source
    }

    /// Neither route may create a project itself: setup's Where it lives is the one place a
    /// project is made (`createProject` from `NewProjectStore`), so the two routes cannot start
    /// producing different projects again.
    func testBothRoutesOpenSetupAndCreateNothingThemselves() throws {
        let window = try Self.appSource("App/LibraryWindow+Actions.swift")
        let menu = try Self.appSource("App/Menus/FileMenuCommands.swift")
        XCTAssertTrue(window.contains("showingNewProjectSetUp = true"), "the window route opens setup")
        XCTAssertTrue(menu.contains("libraryManager.newProjectSetUpRequested = true"), "the windowless route asks for setup")
        for source in [window, menu] {
            XCTAssertFalse(source.contains("createProject(at:"), "a route creates a project outside setup")
        }
    }

    /// #4062 must survive: Set Up New Project… in a window works in that window and does not
    /// open another; the made project is shown in place when setup ends.
    func testInWindowRouteDoesNotOpenAWindow() throws {
        let source = try Self.appSource("App/LibraryWindow+Actions.swift")
        let start = try XCTUnwrap(source.range(of: "func handleNewLibrary() {"))
        let end = try XCTUnwrap(
            source.range(of: "func handleSaveLibrary() {", range: start.lowerBound..<source.endIndex)
        )
        let body = String(source[start.lowerBound..<end.lowerBound])
        XCTAssertFalse(body.contains("openWindow(id:"))
        let window = try Self.appSource("App/LibraryWindow.swift")
        XCTAssertTrue(window.contains("NewProjectSetUpSheet(isPresented: $showingNewProjectSetUp) { assignLibrary(id: $0) }"),
                      "the project setup made is shown in THIS window")
    }
}
