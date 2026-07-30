import SwiftUI

// MARK: - Canvas key-modifier tracking (#3084 / #3086 / #4290)

/// Tracks the canvas renderers' gesture modifiers — ⇧ = marquee (2D), ⌥ =
/// pan (3D background) / force-link (drag-onto, both), and Space = pan the 2D
/// view (#4290). One shared modifier so the 2D and 3D shells don't each
/// re-implement it. macOS-only; a no-op elsewhere.
///
/// Space is the pan modifier because the plain drag belongs to the ITEM: on a
/// Tinderbox-style canvas, dragging a card must move that card, and moving the
/// VIEW is the deliberate act. That is the opposite of what the 2D canvas
/// shipped with, where any plain drag panned the camera and competed with the
/// card drag (#4290).
struct CanvasModifierTracker: ViewModifier {
    var shiftHeld: Binding<Bool>?
    var optionHeld: Binding<Bool>?
    /// Space held → pan-the-view mode. Nil for hosts that don't pan on Space
    /// (the 3D shell, which pans on ⌥).
    var spaceHeld: Binding<Bool>?

    func body(content: Content) -> some View {
        #if canImport(AppKit)
        content
            .onModifierKeysChanged(mask: [.shift, .option]) { _, modifiers in
                shiftHeld?.wrappedValue = modifiers.contains(.shift)
                optionHeld?.wrappedValue = modifiers.contains(.option)
            }
            // `.ignored` so Space still reaches anything else that wants it
            // (Quick Look, scroll) — this only observes the hold, it doesn't
            // claim the key. Requires the host to be `.focusable()`.
            .onKeyPress(.space, phases: [.down, .up]) { keyPress in
                spaceHeld?.wrappedValue = keyPress.phase == .down
                return .ignored
            }
        #else
        content
        #endif
    }
}
