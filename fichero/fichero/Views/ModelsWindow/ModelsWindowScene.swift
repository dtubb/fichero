#if os(macOS)
import SwiftUI

/// The Models and Cluster window's scene (`models.window.is-activitys-shape`, #6588): one `Window`, so there is one copy;
/// its automatic Window-menu item opens it. It replaces `.newItem` with the same File menu as the Activity scene (#4331),
/// so the File menu never goes empty.
struct ModelsWindowScene: Scene {
    let appState: AppState
    let libraryManager: LibraryManager
    let observer: WorkflowExecutionObserver

    var body: some Scene {
        Window("Models & Cluster", id: ModelsWindowModel.windowID) {
            ModelsWindow()
                .environment(appState)
                .environment(libraryManager)
                .environment(observer)
        }
        .defaultSize(width: 1100, height: 620)
        .commands {
            CommandGroup(replacing: .newItem) {
                FileMenuCommands()
                    .environment(libraryManager)
            }
        }
    }
}
#endif
