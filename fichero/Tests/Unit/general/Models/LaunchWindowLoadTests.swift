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
}
