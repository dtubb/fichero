@testable import Fichero
import XCTest

/// #5822: a library-scoped load (automation, activity) asks only libraries the engine has opened;
/// before that it has nothing to ask and nothing to show, and it runs again when the library loads.
final class LibraryScopedLoadReadinessTests: XCTestCase {
    func testNothingIsAskedBeforeAnyLibraryHasLoaded() {
        let open = [UUID(), UUID()]
        XCTAssertEqual(librariesReadyToLoad(open: open, loaded: []), [])
    }

    func testOnlyLoadedLibrariesAreAskedOnceTheyLoad() {
        let first = UUID()
        let second = UUID()
        XCTAssertEqual(librariesReadyToLoad(open: [first, second], loaded: [second]), [second])
        XCTAssertEqual(librariesReadyToLoad(open: [first, second], loaded: [first, second]), [first, second])
    }

    func testALoadedButNoLongerOpenLibraryIsNotAsked() {
        XCTAssertEqual(librariesReadyToLoad(open: [], loaded: [UUID()]), [])
    }
}
