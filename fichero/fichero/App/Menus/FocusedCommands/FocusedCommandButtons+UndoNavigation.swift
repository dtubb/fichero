import SwiftUI

// MARK: - Back and Forward

/// View-menu "Back" — steps the focused window's navigation history back one
/// entry (#3581). Mirrors the content-column toolbar button's ⌘' shortcut and
/// enabled state; disabled when there's no focused window or nothing to go back to.
struct NavigateBackButton: View {
    @FocusedValue(\.navigateBackAction) private var navigateBackAction

    var body: some View {
        Button("Back") {
            navigateBackAction?.run()
        }
        .keyboardShortcut("'", modifiers: [.command])
        .disabled(!(navigateBackAction?.isEnabled ?? false))
    }
}

/// View-menu "Forward" — the ⌘⇧' counterpart to `NavigateBackButton` (#3581).
struct NavigateForwardButton: View {
    @FocusedValue(\.navigateForwardAction) private var navigateForwardAction

    var body: some View {
        Button("Forward") {
            navigateForwardAction?.run()
        }
        .keyboardShortcut("'", modifiers: [.command, .shift])
        .disabled(!(navigateForwardAction?.isEnabled ?? false))
    }
}

/// ⌘Z (#5658, ruled per window 2026-10-11): typing in a focused field first, then the image
/// editor's last step, then the KEY WINDOW's own steps (`WindowSteps`), newest first, named by the
/// step ("Undo Move", "Undo Delete 3 Items"). Disabled while one of the window's calls is out
/// (`undo.window.in-flight`). Never Back, and never another window's or another person's change:
/// those are taken back from the history list. A refusal is shown in the window that asked
/// (`UndoRefusalNotice`).
@MainActor
struct UndoLastActionButton: View {
    @FocusedValue(\.windowSteps) private var windowSteps
    /// The mounted image editor's undo-last-step (Daniel, 2026-08-31).
    @FocusedValue(\.imageEditUndoAction) private var imageEditUndoAction

    var body: some View {
        Button(undoTitle) {
            performUndo()
        }
        .keyboardShortcut("z", modifiers: .command)
        .disabled(route == .none)
        .accessibilityIdentifier("edit.undo")
    }

    /// Where this ⌘Z should land right now (#4354). The menu item is a key
    /// equivalent, so it matches ahead of the responder chain; the route puts
    /// the focused text editor back in front of the window's steps.
    ///
    /// Recomputed on every body evaluation, which is when AppKit rebuilds the
    /// menu (menu validation runs before display and before a key equivalent
    /// fires), so the focus probe is read at the moment it matters.
    private var route: UndoRoute {
        _ = windowSteps?.revision
        return UndoRoutingPolicy.route(
            isTextEditing: FocusedTextResponder.isEditing,
            textUndoAvailable: FocusedTextResponder.canUndo,
            imageEditUndoEnabled: imageEditUndoAction?.isEnabled == true,
            windowUndoAvailable: windowSteps?.canUndo == true
        )
    }

    private var undoTitle: String {
        switch route {
        case .imageEdit: "Undo Edit"
        case .windowStep: windowSteps?.undoName.map { "Undo \($0)" } ?? "Undo"
        case .focusedTextEditor, .none: "Undo"
        }
    }

    private func performUndo() {
        switch route {
        case .none:
            return
        case .focusedTextEditor:
            // Hand it back to the editor that has focus — the shape the
            // responder chain would have produced if a key equivalent did not
            // match first (#4354).
            FocusedTextResponder.undo()
        case .imageEdit:
            imageEditUndoAction?.run()
        case .windowStep:
            windowSteps?.undo()
        }
    }
}

// MARK: - Redo (menu audit 2026-09-17)

/// ⌘⇧Z — typing in a focused field first, then the key window's steps (#5658): it puts back what
/// ⌘Z in this window took back, by the rows that undo wrote. Disabled while one of the window's
/// calls is out.
@MainActor
struct RedoLastActionButton: View {
    @FocusedValue(\.windowSteps) private var windowSteps

    var body: some View {
        Button(redoTitle) {
            performRedo()
        }
        .keyboardShortcut("z", modifiers: [.command, .shift])
        .disabled(route == .none)
        .accessibilityIdentifier("edit.redo")
    }

    private var route: RedoRoute {
        _ = windowSteps?.revision
        return RedoRoutingPolicy.route(
            isTextEditing: FocusedTextResponder.isEditing,
            textRedoAvailable: FocusedTextResponder.canRedo,
            windowRedoAvailable: windowSteps?.canRedo == true
        )
    }

    private var redoTitle: String {
        guard route == .windowStep, let name = windowSteps?.redoName else { return "Redo" }
        return "Redo \(name)"
    }

    private func performRedo() {
        switch route {
        case .none:
            return
        case .focusedTextEditor:
            FocusedTextResponder.redo()
        case .windowStep:
            windowSteps?.redo()
        }
    }
}
