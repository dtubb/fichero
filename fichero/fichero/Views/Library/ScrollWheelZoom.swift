#if canImport(AppKit)
import AppKit
import SwiftUI

// MARK: - Scroll Wheel Zoom (AppKit bridge for scroll wheel)

struct ScrollWheelZoomView: NSViewRepresentable {
    @Binding var scale: CGFloat
    let minScale: CGFloat
    let maxScale: CGFloat

    func makeNSView(context: Context) -> NSView {
        let view = ScrollWheelCaptureView()
        view.onScroll = { delta in
            let newScale = scale + delta * 0.01
            scale = min(max(newScale, minScale), maxScale)
        }
        return view
    }

    func updateNSView(_ nsView: NSView, context: Context) {}
}

class ScrollWheelCaptureView: NSView {
    var onScroll: ((CGFloat) -> Void)?

    override func scrollWheel(with event: NSEvent) {
        // Use pinch gesture delta (magnification) or scroll delta
        if event.phase == .changed || event.momentumPhase == .changed {
            let delta = event.scrollingDeltaY
            onScroll?(delta)
        }
    }

    override var acceptsFirstResponder: Bool { true }
}
#else
import SwiftUI

struct ScrollWheelZoomView: View {
    @Binding var scale: CGFloat
    let minScale: CGFloat
    let maxScale: CGFloat

    var body: some View {
        EmptyView()
    }
}
#endif

