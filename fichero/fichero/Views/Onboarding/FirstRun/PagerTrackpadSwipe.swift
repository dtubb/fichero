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
private struct TrackpadSwipe: ViewModifier {
    let move: (Bool) -> Void
    @State private var monitor: Any?

    func body(content: Content) -> some View {
        content
            .onAppear {
                guard monitor == nil else { return }
                var travelled = CGSize.zero
                var fired = false
                monitor = NSEvent.addLocalMonitorForEvents(matching: .scrollWheel) { event in
                    guard event.window?.isKeyWindow == true, event.hasPreciseScrollingDeltas else { return event }
                    if event.phase == .began { travelled = .zero; fired = false }
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
