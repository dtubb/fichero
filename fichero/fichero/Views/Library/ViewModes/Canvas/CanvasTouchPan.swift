#if canImport(UIKit)
import SwiftUI
import UIKit

// MARK: - Two-finger drag → camera pan, on touch (#4408)

/// The iPad half of #4408.
///
/// The macOS half wired two-finger *scroll* to the camera. On a touch device
/// there is no scroll event and no Space key, and the canvas's one-finger drag
/// is already spoken for: it is the marquee (and, on a card, a node drag). So
/// panning a spatial canvas on iPad was not merely awkward, it was **not
/// possible at all** — the only pan path in the app was `spaceHeld`, and iPad
/// has no Space to hold.
///
/// Two fingers is the unambiguous idiom — Maps, Photos, Freeform — and it is
/// unambiguous here for a mechanical reason as well as a conventional one: it
/// is a different touch COUNT from every gesture the canvas already claims, so
/// it cannot steal a marquee or a node drag. That is why this needed no design
/// decision.
///
/// It deliberately DOES run alongside pinch-zoom, which is also two fingers.
/// Two fingers that move together pan and two that spread zoom, simultaneously,
/// is what every map on the platform does; refusing simultaneity would make a
/// pinch that drifts feel broken.
///
/// A UIKit bridge for the same reason the macOS side is an AppKit one: SwiftUI
/// has no touch-count-qualified drag. This is the mirror of
/// `CanvasScrollPan.swift`, and both hand their caller a `CGSize` shaped like a
/// drag translation so the SAME conversion the drag path uses can consume it.
struct CanvasTouchPanView: UIViewRepresentable {
    /// Incremental translation in view POINTS since the last callback, shaped
    /// like a drag translation.
    let onPan: (CGSize) -> Void

    func makeUIView(context: Context) -> UIView {
        let view = CanvasTouchPanCaptureView()
        view.onPan = onPan
        view.backgroundColor = .clear
        let recognizer = UIPanGestureRecognizer(
            target: view,
            action: #selector(CanvasTouchPanCaptureView.handlePan(_:))
        )
        // Exactly two. One finger stays with the marquee; three or more belong
        // to the system (app switcher, split view) and must not be intercepted.
        recognizer.minimumNumberOfTouches = 2
        recognizer.maximumNumberOfTouches = 2
        recognizer.delegate = view
        view.addGestureRecognizer(recognizer)
        return view
    }

    func updateUIView(_ uiView: UIView, context: Context) {
        (uiView as? CanvasTouchPanCaptureView)?.onPan = onPan
    }
}

final class CanvasTouchPanCaptureView: UIView, UIGestureRecognizerDelegate {
    var onPan: ((CGSize) -> Void)?

    /// Transparent to everything except its own recognizer — the same contract
    /// the macOS capture view has via `hitTest`. Without it, wiring pan would
    /// swallow taps and one-finger drags meant for the SwiftUI content below.
    override func point(inside point: CGPoint, with event: UIEvent?) -> Bool { false }

    /// Pinch and two-finger pan must both be live at once; see the type doc.
    func gestureRecognizer(
        _ gestureRecognizer: UIGestureRecognizer,
        shouldRecognizeSimultaneouslyWith other: UIGestureRecognizer
    ) -> Bool { true }

    @objc
    func handlePan(_ recognizer: UIPanGestureRecognizer) {
        guard let view = recognizer.view else { return }
        let translation = recognizer.translation(in: view)
        // INCREMENTAL, not cumulative: `panCamera` applies a delta to the
        // current camera, so feeding it the running total would accelerate the
        // pan quadratically. Reset after each read — the same shape the macOS
        // scroll path gets for free, since a scroll event IS a delta.
        recognizer.setTranslation(.zero, in: view)

        guard translation != .zero else { return }
        // No direction inversion here. `isDirectionInvertedFromDevice` exists
        // because macOS "natural scrolling" flips a scroll event before the app
        // sees it; a touch translation is the finger's actual movement, and
        // content should follow the finger. Copying the macOS un-flip would
        // invert iPad for everyone.
        onPan?(CGSize(width: translation.x, height: translation.y))
    }
}
#endif
