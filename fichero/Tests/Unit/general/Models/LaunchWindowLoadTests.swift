@testable import Fichero
import XCTest

/// A launch window that began before the engine was ready asks again once it is (#7078): the library load it
/// began parked (no engine yet, or a grant gate), and nothing re-asked, so the pane said "Loading documents…"
/// for good while a window opened later read the library at once.
final class LaunchWindowLoadTests: XCTestCase {
    func testAWindowAsksForALoadWhenTheEngineIsReadyAndTheLibraryIsNeitherLoadedNorLoading() {
        XCTAssertTrue(LibraryManager.windowShouldAskForLoad(engineReady: true, loaded: false, loading: false))
    }

    func testAWindowDoesNotAskBeforeTheEngineIsReady() {
        XCTAssertFalse(LibraryManager.windowShouldAskForLoad(engineReady: false, loaded: false, loading: false))
    }

    func testAWindowDoesNotAskForALibraryThatIsLoadedOrLoading() {
        XCTAssertFalse(LibraryManager.windowShouldAskForLoad(engineReady: true, loaded: true, loading: false))
        XCTAssertFalse(LibraryManager.windowShouldAskForLoad(engineReady: true, loaded: false, loading: true))
    }

    func testTheReaskKeepsAGrantGateThatIsStillSet() async {
        // A grant in flight holds the gate; the engine-ready re-ask must not release it (#3986-A, #3773).
        let manager = LibraryManager.shared
        let library = manager.createNewLibrary()
        manager.backendIsReady = true
        manager.libraryIdsAwaitingGrant.insert(library.id)
        defer { manager.libraryIdsAwaitingGrant.remove(library.id) }

        await manager.askForLoadOnEngineReady(library, engineReady: true)

        XCTAssertTrue(manager.libraryIdsAwaitingGrant.contains(library.id), "the re-ask released a gate in flight")
        XCTAssertFalse(manager.loadingLibraryIds.contains(library.id))
        XCTAssertFalse(manager.loadedLibraryIds.contains(library.id))
    }

    func testAFailedGrantClearsItsOwnGate() {
        let manager = LibraryManager.shared
        let library = manager.createNewLibrary()
        manager.libraryIdsAwaitingGrant.insert(library.id)

        manager.grantDidFail(for: library)

        XCTAssertFalse(manager.libraryIdsAwaitingGrant.contains(library.id))
    }

    func testTheBackgroundReaskReturnsAtOnceAndKeepsAGateThatIsSet() async {
        // Called without `await`: the caller is not held while the load runs (#7078).
        let manager = LibraryManager.shared
        let library = manager.createNewLibrary()
        manager.backendIsReady = true
        manager.libraryIdsAwaitingGrant.insert(library.id)
        defer { manager.libraryIdsAwaitingGrant.remove(library.id) }

        let task = manager.askForLoadOnEngineReadyInBackground(library, engineReady: true)
        await task.value

        XCTAssertTrue(manager.libraryIdsAwaitingGrant.contains(library.id))
        XCTAssertFalse(manager.loadingLibraryIds.contains(library.id))
    }
}
