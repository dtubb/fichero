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
            // Menu audit 2026-09-17: ⌘9 is shared with the image/reader
            // preview's own "Zoom to Fit" (ImagePreviewMenuCommands.swift) —
            // deliberately: `hasFocusedCanvas` here and `hasActiveImagePreview`
            // there are mutually exclusive, so one verb keeps one chord across
            // both contexts. Review 2026-09-17 (#4693) moved this OFF ⌘= (was
            // briefly unified there): AppKit's key-equivalent matching for an
            // item whose mask omits `.shift` checks `charactersIgnoringModifiers`,
            // which strips Shift back to the unshifted base character — so a
            // ⌘= item ALSO matches ⌘⇧= (i.e. ⌘+), racing "Zoom In"'s own ⌘+ and
            // winning because it appears earlier in the menu. ⌘9 shares no
            // physical key with the +/- zoom chords, so it can't repeat that.
            Button("Zoom to Fit") {
                canvasActions?.zoomToFit()
            }
            .keyboardShortcut("9", modifiers: [.command])
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
