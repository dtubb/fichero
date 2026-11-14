//
//  StoppedAtQuitAlertModifier.swift
//  Fichero
//
//  Mounts the launch alert of `activity.launch.nothing-starts-one-alert` (#6584) over the main window: asked once per
//  project as it opens; Leave Paused is the default.
//

import SwiftUI

struct StoppedAtQuitAlertModifier: ViewModifier {
    @Environment(\.openWindow) private var openWindow
    let libraryManager: LibraryManager
    @State private var alert = StoppedAtQuitAlert()

    private var libraries: [LibraryManager.LibraryReference] { libraryManager.openLibraries }

    func body(content: Content) -> some View {
        content
            .task(id: libraries.map(\.id)) { await alert.check(libraries: libraries) }
            .alert(alert.title, isPresented: Bindable(alert).isPresented) {
                Button("Leave Paused") { alert.leavePaused() }.keyboardShortcut(.defaultAction)
                Button("Choose…") {
                    alert.leavePaused()
                    openWindow(id: ActivityWindowSelectionState.monitorWindowID)
                }
                Button("Continue All") { Task { await alert.continueAll(libraries: libraries) } }
            } message: {
                Text(alert.message)
            }
    }
}
