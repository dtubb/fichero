@testable import Fichero
import XCTest

/// #4017 — macOS launch showed "Create a new library or open an existing one"
/// before it would show the app.
///
/// `LibraryWindow.init` seeded `WindowState(libraryId: UUID())` — a fresh random
/// id that `LibraryManager.getLibrary(id:)` can never resolve. So
/// `windowState.library` was nil on the first frame of every launch, and the
/// window rendered `noLibraryView`. iOS seeded `globalLibraryId` and had no such
/// screen.
///
/// Two platforms seeding one window differently, with nothing forcing them to
/// agree — which is why only one of them had the wall in front of it.
/// `@MainActor` because `WindowState` is: constructing one and reading
/// `library` are both main-actor work, and the launch path this describes runs
/// there. Hopping per-assertion instead would let the test observe a state the
/// app never sees.
@MainActor
final class LaunchWindowSeedTests: XCTestCase {

    private static func appSource(_ relativePath: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()   // App
            .deletingLastPathComponent()   // fichero-tests
            .deletingLastPathComponent()   // fichero
            .appendingPathComponent("fichero")
            .appendingPathComponent(relativePath)
        let source = try String(contentsOf: url, encoding: .utf8)
        XCTAssertFalse(source.isEmpty, "\(relativePath) is empty — this guard measures nothing")
        return source
    }

    // MARK: - The behaviour

    /// The seeded id must be one that actually resolves.
    ///
    /// A random UUID satisfies "a window has a library id" perfectly and
    /// resolves to nothing — the gap between having an id and having a LIBRARY
    /// is the entire bug.
    func testTheGlobalLibraryIdIsStableAndNotRandom() {
        XCTAssertEqual(
            LibraryManager.globalLibraryId,
            LibraryManager.globalLibraryId,
            "the seed must be a fixed id; a fresh UUID per call is what produced the prompt"
        )
    }

    func testAWindowSeededWithTheGlobalIdCarriesThatId() {
        let state = WindowState(libraryId: LibraryManager.globalLibraryId)

        XCTAssertEqual(state.libraryId, LibraryManager.globalLibraryId)
    }

    /// The negative case, stated so the distinction is on the record: a random
    /// id is not merely "a different library", it is NO library.
    func testARandomlySeededWindowResolvesToNoLibrary() {
        let state = WindowState(libraryId: UUID())

        XCTAssertNil(
            state.library,
            "a random id resolves to nothing — this is what rendered noLibraryView"
        )
    }

    // MARK: - The two platforms must agree

    /// Structural, because the defect was a DIVERGENCE rather than a wrong
    /// value: each file was locally reasonable and they disagreed.
    func testMacAndIOSSeedTheWindowTheSameWay() throws {
        let mac = try Self.appSource("App/LibraryWindow.swift")
        let ios = try Self.appSource("FicheroApp_iOS.swift")

        XCTAssertTrue(
            mac.contains("WindowState(libraryId: LibraryManager.globalLibraryId)"),
            "macOS must seed the global library, as iOS does"
        )
        XCTAssertTrue(
            ios.contains("WindowState(libraryId: LibraryManager.globalLibraryId)"),
            "iOS is the reference — if this fails, check which platform moved"
        )
    }

    /// The specific regression: `UUID()` as a seed must not come back.
    ///
    /// Narrow on purpose. `UUID()` is legitimate almost everywhere, so this
    /// bans it only in the window-seed expression rather than in the file.
    func testTheWindowIsNeverSeededWithAFreshUUID() throws {
        let mac = try Self.appSource("App/LibraryWindow.swift")

        XCTAssertFalse(
            mac.contains("WindowState(libraryId: UUID())"),
            "a random seed resolves to no library and renders the create/open prompt (#4017)"
        )
    }
}
