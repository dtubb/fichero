@testable import Fichero
import SwiftUI
import XCTest

/// `source.onboard.stages.try-progress-in-place` and the stage pictures (review 360): Set Up is presented as a sheet of
/// the library window, above the tree that injects the project's services. Hosted the way the window hosts it (the
/// sheet's own modifier, not a hand-copied list), what Set Up's pictures read must be there.
@MainActor
final class SetUpSheetEnvironmentTests: XCTestCase {
    func testTheSetUpSheetGetsTheProjectsStorageServiceAndTheAppState() {
        final class Seen {
            var storage: StorageService?
            var appState: AppState?
        }
        // What `LibraryImageView` (the sample pages' thumbnails, the compare window's picture) and the window read.
        struct Probe: View {
            let seen: Seen
            @Environment(StorageService.self) private var storage: StorageService?
            @Environment(AppState.self) private var appState: AppState?
            var body: some View {
                seen.storage = storage
                seen.appState = appState
                return Color.clear
            }
        }
        let seen = Seen()
        let library = LibraryPreviewFixtures.library
        let appState = AppState()
        let host = NSHostingView(rootView: Probe(seen: seen)
            .modifier(SetUpSheetEnvironment(appState: appState, library: library)))
        host.frame = CGRect(x: 0, y: 0, width: 80, height: 80)
        host.layoutSubtreeIfNeeded()
        XCTAssertTrue(seen.storage === library.storageService, "Set Up's pictures are drawn from the project's storage")
        XCTAssertTrue(seen.appState === appState)
    }

    /// A new project is made INSIDE the window (Your project), so the services follow the window's own `project`: none
    /// before it exists (no crash, no placeholder service), the project's once it does.
    func testTheServicesFollowTheProjectTheWindowMakes() {
        final class Seen { var storage: StorageService? }
        struct Probe: View {
            let seen: Seen
            @Environment(StorageService.self) private var storage: StorageService?
            var body: some View {
                seen.storage = storage
                return Color.clear
            }
        }
        let seen = Seen()
        let appState = AppState()
        let before = NSHostingView(rootView: Probe(seen: seen)
            .modifier(SetUpSheetEnvironment(appState: appState, library: nil)))
        before.frame = CGRect(x: 0, y: 0, width: 80, height: 80)
        before.layoutSubtreeIfNeeded()
        XCTAssertNil(seen.storage, "no project yet: nothing to draw from, and nothing crashes")
        let library = LibraryPreviewFixtures.library
        let after = NSHostingView(rootView: Probe(seen: seen)
            .modifier(SetUpSheetEnvironment(appState: appState, library: library)))
        after.frame = CGRect(x: 0, y: 0, width: 80, height: 80)
        after.layoutSubtreeIfNeeded()
        XCTAssertTrue(seen.storage === library.storageService, "a project made in the window gets its own services")
    }
}
