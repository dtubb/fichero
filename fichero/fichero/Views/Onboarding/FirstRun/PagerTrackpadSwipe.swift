import SwiftUI

/// Two-finger trackpad swipe for the wide Set Up pager (`wide.pager.*`, #5668): one gesture moves at most one page. macOS only;
/// elsewhere the drag gesture on `PagerBinding` covers touch.
extension View {
    func trackpadSwipe(_ move: @escaping (Bool) -> Void) -> some View {
        #if os(macOS)
        modifier(TrackpadSwipe(move: move))
        #else
        self
        #endif
    }
}

#if os(macOS)
/// Whether a horizontal scroll that starts at `point` of `window` belongs to a horizontal scroller (a strip of pictures): that
/// scroll scrolls the strip, never the pager.
@MainActor
private func startsOverAHorizontalScroller(_ event: NSEvent) -> Bool {
    var view = event.window?.contentView?.hitTest(event.locationInWindow)
    while let current = view {
        if let scroller = current as? NSScrollView, let document = scroller.documentView,
           document.frame.width > scroller.contentSize.width + 1 { return true }
        view = current.superview
    }
    return false
}

/// The window the modifier sits in, found once the view is on screen.
private struct OwnWindow: NSViewRepresentable {
    let found: (NSWindow?) -> Void
    func makeNSView(context: Context) -> NSView {
        let view = NSView()
        DispatchQueue.main.async { found(view.window) }
        return view
    }
    func updateNSView(_ view: NSView, context: Context) { found(view.window) }
}

private struct TrackpadSwipe: ViewModifier {
    let move: (Bool) -> Void
    @State private var monitor: Any?
    @State private var window: NSWindow?

    func body(content: Content) -> some View {
        content
            .background(OwnWindow { window = $0 })
            .onAppear {
                guard monitor == nil else { return }
                var travelled = CGSize.zero
                var fired = false
                var ignored = false
                monitor = NSEvent.addLocalMonitorForEvents(matching: .scrollWheel) { event in
                    // Only this Set Up window: a scroll in a sheet or Settings never moves the page underneath.
                    guard let own = window, event.window === own, event.hasPreciseScrollingDeltas else { return event }
                    if event.phase == .began {
                        travelled = .zero
                        fired = false
                        ignored = startsOverAHorizontalScroller(event)
                    }
                    guard !ignored else { return event }
                    travelled.width += event.scrollingDeltaX
                    travelled.height += event.scrollingDeltaY
                    if !fired, abs(travelled.width) > 80, abs(travelled.width) > 2 * abs(travelled.height) {
                        fired = true
                        move(travelled.width < 0)
                    }
                    return event
                }
            }
            .onDisappear {
                if let monitor { NSEvent.removeMonitor(monitor) }
                monitor = nil
            }
    }
}
#endif
