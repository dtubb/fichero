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
}
