import SwiftUI

// MARK: - Canvas camera commands (§16, R10 step 4)

/// The View menu's Canvas section: zoom to fit, and walking the jump history.
///
/// R10 settles what navigation on a board is — **the cards move, the camera
/// cuts, the user never flies**. So these are jump-cuts: ⌘= frames everything,
/// ⌘[ and ⌘] walk back and forward through the poses you jumped FROM. There is
/// deliberately no "fly to" anything; the only continuous motion on a canvas
/// stays the pointer-anchored zoom the user drives frame by frame.
///
/// The whole section disables itself when no canvas is focused: `canvasActions`
/// is nil in List, Table or Reader, and a control that cannot apply should not
/// tease (dead-simple-UX). Same shape as `ImagePreviewMenuCommands`.
struct CanvasViewSection: View {
    @FocusedValue(\.canvasViewActions) private var canvasActions
    private var hasFocusedCanvas: Bool { canvasActions != nil }

    var body: some View {
        Section("Canvas") {
            Button("Zoom to Fit") {
                canvasActions?.zoomToFit()
            }
            .keyboardShortcut("=", modifiers: [.command])
            .disabled(!hasFocusedCanvas)

            Button("Jump Back") {
                canvasActions?.jumpBack()
            }
            .keyboardShortcut("[", modifiers: [.command])
            .disabled(!hasFocusedCanvas || canvasActions?.canJumpBack != true)

            Button("Jump Forward") {
                canvasActions?.jumpForward()
            }
            .keyboardShortcut("]", modifiers: [.command])
            .disabled(!hasFocusedCanvas || canvasActions?.canJumpForward != true)
        }
    }
}
