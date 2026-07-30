#if canImport(AppKit)
import AppKit
import SwiftUI

// MARK: - Two-finger scroll → camera pan (#4408)

/// Feeds scroll deltas to the canvas camera.
///
/// The pan already worked: `CanvasOrtho2DRenderer.panCamera(worldDelta:)` has
/// existed since #3083 and had exactly one caller — the Space-held drag. Scroll
/// was never wired, so panning required holding Space, which is not how anyone
/// expects to move around a canvas.
///
/// Nothing new is built here. This is a second INPUT to the same camera, and it
/// converts through the same `Canvas2DProjection.cameraPanDelta` calibration
/// that pan, node-drag and marquee already share — one knob, not a second scale
/// factor sitting beside it.
///
/// An AppKit bridge because SwiftUI has no scroll-wheel gesture for an
/// arbitrary view. Mirrors `Views/Preview/ImageViewer/ScrollWheelZoom.swift`,
/// the sanctioned bridge already doing this for zoom — two axes instead of one.
struct CanvasScrollPanView: NSViewRepresentable {
    /// Scroll delta in view POINTS, already corrected for scroll direction.
    /// Shaped like a drag translation so the caller can hand it to the same
    /// conversion a drag uses.
    let onScroll: (CGSize) -> Void

    func makeNSView(context: Context) -> NSView {
        let view = CanvasScrollCaptureView()
        view.onScroll = onScroll
        return view
    }

    func updateNSView(_ nsView: NSView, context: Context) {
        (nsView as? CanvasScrollCaptureView)?.onScroll = onScroll
    }
}

final class CanvasScrollCaptureView: NSView {
    var onScroll: ((CGSize) -> Void)?

    /// Transparent to every other input: this view exists only to receive
    /// scroll, so clicks, drags and taps must continue to the SwiftUI content
    /// underneath. Without this, wiring pan would break selection and node drag.
    override func hitTest(_ point: NSPoint) -> NSView? { nil }

    override func scrollWheel(with event: NSEvent) {
        // Momentum and inertial phases are deliberately NOT filtered out.
        // Stopping at `.ended` cuts the glide short and makes trackpad panning
        // feel dead — the phase is exactly the part that feels like a canvas.
        var deltaX = event.scrollingDeltaX
        var deltaY = event.scrollingDeltaY

        // `isDirectionInvertedFromDevice` reports that the OS already flipped
        // these for the user's "natural scrolling" preference. Un-flip so the
        // gesture agrees with Space-drag, which moves the view WITH the
        // pointer — two inputs, one on-screen result. Read rather than
        // hardcoded: a hardcoded sign is right for half the users and feels
        // broken in a way they cannot articulate.
        if event.isDirectionInvertedFromDevice {
            deltaX = -deltaX
            deltaY = -deltaY
        }

        guard deltaX != 0 || deltaY != 0 else { return }
        onScroll?(CGSize(width: deltaX, height: deltaY))
    }
}
#endif
