import SwiftUI

/// ⌘ + scroll wheel (or a Magic Mouse's swipe) zooms the view under the pointer (owner 2026-11-13,
/// `panes.chrome.command-scroll-zooms`), as the Canvas already does (`CanvasScrollPan`): one step per scroll event that
/// moves, in, toward the reader, for a scroll up. Without ⌘ a scroll is a scroll.
enum CommandScrollZoom {
    /// The zoom step one scroll event asks for: +1 in, −1 out, nil when ⌘ is not held or the wheel did not move.
    static func step(deltaY: CGFloat, commandHeld: Bool) -> Int? {
        guard commandHeld, deltaY != 0 else { return nil }
        return deltaY > 0 ? 1 : -1
    }
}

#if canImport(AppKit)
// NSEvent comes through SwiftUI on macOS; no AppKit import (check_appkit_imports).
private struct CommandScrollZoomModifier: ViewModifier {
    let onStep: (Int) -> Void
    @State private var hovering = false
    @State private var monitor: Any?

    func body(content: Content) -> some View {
        content
            .onHover { hovering = $0 }
            .onAppear {
                monitor = NSEvent.addLocalMonitorForEvents(matching: .scrollWheel) { event in
                    guard hovering, let step = CommandScrollZoom.step(
                        deltaY: event.scrollingDeltaY, commandHeld: event.modifierFlags.contains(.command))
                    else { return event }
                    onStep(step)
                    return nil  // the zoom took the event: the view under it does not also scroll
                }
            }
            .onDisappear {
                if let monitor { NSEvent.removeMonitor(monitor) }
                monitor = nil
            }
    }
}
#endif

extension View {
    /// Zoom by ⌘ + scroll while the pointer is over this view (`CommandScrollZoom`); a no-op on touch.
    @ViewBuilder
    func commandScrollZoom(_ onStep: @escaping (Int) -> Void) -> some View {
        #if canImport(AppKit)
        modifier(CommandScrollZoomModifier(onStep: onStep))
        #else
        self
        #endif
    }
}
