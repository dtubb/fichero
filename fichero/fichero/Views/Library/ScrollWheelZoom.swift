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

#elseif canImport(UIKit)
import SwiftUI
import UIKit

// MARK: - Pinch Zoom (UIKit bridge)

struct ScrollWheelZoomView: UIViewRepresentable {
    @Binding var scale: CGFloat
    let minScale: CGFloat
    let maxScale: CGFloat

    func makeUIView(context: Context) -> UIView {
        let view = PinchZoomCaptureView()
        view.onScaleDelta = { delta in
            let newScale = scale * delta
            scale = min(max(newScale, minScale), maxScale)
        }
        return view
    }

    func updateUIView(_ uiView: UIView, context: Context) {}
}

class PinchZoomCaptureView: UIView {
    var onScaleDelta: ((CGFloat) -> Void)?
    private var previousScale: CGFloat = 1.0

    override init(frame: CGRect) {
        super.init(frame: frame)
        let pinch = UIPinchGestureRecognizer(target: self, action: #selector(handlePinch(_:)))
        addGestureRecognizer(pinch)
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    @objc private func handlePinch(_ gesture: UIPinchGestureRecognizer) {
        switch gesture.state {
        case .began:
            previousScale = gesture.scale
        case .changed:
            let delta = gesture.scale / previousScale
            previousScale = gesture.scale
            onScaleDelta?(delta)
        default:
            break
        }
    }
}

#endif
