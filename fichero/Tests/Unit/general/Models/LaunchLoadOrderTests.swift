@testable import Fichero
import XCTest

/// Launch does the front library's work first, and only the grants the opening libraries need (#5228, #5251).
/// Daniel, 2026-09-28: launch "takes a really long time" -- 24 s measured restoring seven libraries one after
/// another, after a sweep that re-sent every bookmark ever stored. What breaks without these: the window waits
/// for every library again, or a library's own grant is left out and it can't be read.
final class LaunchLoadOrderTests: XCTestCase {
    func testTheFrontLibraryLoadsFirstAndTheRestKeepTheirOrder() {
        let a = UUID(), b = UUID(), c = UUID()
        XCTAssertEqual(LibraryManager.frontFirst([a, b, c], front: c), [c, a, b])
        XCTAssertEqual(LibraryManager.frontFirst([a, b, c], front: nil), [a, b, c])
        XCTAssertEqual(LibraryManager.frontFirst([a, b], front: UUID()), [a, b], "a front that isn't open changes nothing")
    }

    func testOnlyAGrantThatIsOrHoldsALibraryIsResent() {
        let libraries = ["/Users/d/Fichero Test Library/Acceptance.fichero", "/Users/d/Fichero/Marshall.fichero"]
        XCTAssertTrue(FolderAccessManager.grantCoversALibrary("/Users/d/Fichero/Marshall.fichero", libraryPaths: libraries))
        XCTAssertTrue(FolderAccessManager.grantCoversALibrary("/Users/d/Fichero Test Library", libraryPaths: libraries))
        XCTAssertFalse(FolderAccessManager.grantCoversALibrary("/Users/d/Fichero/Black Pacific.fichero", libraryPaths: libraries))
        XCTAssertFalse(FolderAccessManager.grantCoversALibrary("/Users/d/Fichero Test", libraryPaths: libraries),
                       "a sibling whose name is a prefix is not a parent")
    }

    /// #5228: launch reconciled against the KNOWN registry (every library ever added: 15 on the
    /// maintainer's engine) and opened all ten that still existed, when four were open. It opens what the
    /// engine HAS OPEN; the known list only decides drops.
    func testLaunchOpensWhatTheEngineHasOpenNotEveryKnownLibrary() {
        let known = (1...10).map { "/Users/d/Fichero/L\($0).fichero" }
        let engineOpen = ["/Users/d/Fichero/L3.fichero"]
        let appOpen: [(id: UUID, path: String)] = []
        let fromKnown = LibraryManager.registryReconciliation(
            openLibraries: appOpen, registryPaths: known, globalLibraryId: UUID()
        ).pathsToOpen
        let fromEngine = LibraryManager.registryReconciliation(
            openLibraries: appOpen, registryPaths: engineOpen, globalLibraryId: UUID()
        ).pathsToOpen
        XCTAssertEqual(fromKnown.count, 10, "what the old reconcile opened")
        XCTAssertEqual(fromEngine, engineOpen)
    }
}
