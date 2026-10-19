@testable import Fichero
import XCTest

/// spec: modes-to-panes §`m2p.ios.window-state-per-scene` (iOS I1). Each iPad scene owns its
/// WindowState, so the app-wide current library must not move a scene that chose its own.
final class SceneLibrarySelectionTests: XCTestCase {

    func testSceneOnTheGlobalDefaultFollowsTheAppWideLibrary() {
        let current = UUID()
        XCTAssertEqual(
            LibraryWorkspaceSelection.appDefaultLibraryId(
                windowLibraryId: LibraryManager.globalLibraryId, currentLibraryId: current),
            current)
    }

    func testSceneThatChoseItsOwnLibraryIgnoresTheAppWideLibrary() {
        XCTAssertNil(
            LibraryWorkspaceSelection.appDefaultLibraryId(
                windowLibraryId: UUID(), currentLibraryId: UUID()))
    }
}
