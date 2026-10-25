import SwiftUI

/// Cancel in Set Up (#6117).
extension FirstRunWindow {
    /// Cancel deletes the project only when this window made it: File › Set Up New Project… (#6117).
    static func cancelDeletesTheProject(in mode: Mode) -> Bool { mode == .newProject }

    /// Close a setup opened on purpose. A new project's own Set Up deletes what it made, asking first when material
    /// was added; Set Up… on an existing project only closes (its unsaved answers go) (#6117).
    func cancel() {
        guard Self.cancelDeletesTheProject(in: mode), newProject.created != nil else { return finish() }
        if store?.hasMaterial ?? false {
            confirmingCancel = true
        } else {
            discardAndClose()
        }
    }

    func discardAndClose() {
        finishedSetUp = true
        if !newProject.discard(), let why = newProject.errorMessage {
            discardError = why  // the alert's OK closes the window
        } else {
            dismiss()
        }
    }
}
