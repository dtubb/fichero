import SwiftUI

// MARK: - Canvas key-modifier tracking (#3084 / #3086)

/// Tracks ⇧ and ⌥ for the canvas renderers' gestures — ⇧ = marquee (2D), ⌥ =
/// pan (3D background) / force-link (drag-onto, both). One shared modifier so
/// the 2D and 3D shells don't each re-implement it. macOS-only
/// (`onModifierKeysChanged`); a no-op elsewhere.
struct CanvasModifierTracker: ViewModifier {
    var shiftHeld: Binding<Bool>?
    var optionHeld: Binding<Bool>?

    func body(content: Content) -> some View {
        #if canImport(AppKit)
        content.onModifierKeysChanged(mask: [.shift, .option]) { _, modifiers in
            shiftHeld?.wrappedValue = modifiers.contains(.shift)
            optionHeld?.wrappedValue = modifiers.contains(.option)
        }
        #else
        content
        #endif
    }
}
