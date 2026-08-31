#if os(macOS)
import AppKit
import OSLog

// MARK: - Pinch handling (split from the coordinator for file_length).

@MainActor
extension ImageWithCursorTrackingMacCoordinator {
    private func logPinchTriage(state: NSGestureRecognizer.State) {
        guard state == .began else { return }
        Logger(subsystem: "app.fichero.fichero", category: "swipe-triage").info(
            """
            pinch-triage began: \
            loupe=\((self.imageView as? TrackingImageView)?.loupeEnabled ?? false) \
            scrollView=\(self.scrollView != nil)
            """
        )
    }

    @objc func handleMagnify(_ gesture: NSMagnificationGestureRecognizer) {
        // Gesture triage (Daniel, 2026-08-31: pinch still dead in the wild).
        logPinchTriage(state: gesture.state)
        // Check if cursor is over loupe — zoom the loupe instead of the main image.
        if let trackingView = imageView as? TrackingImageView,
           trackingView.loupeEnabled,
           let loupeViewPos = trackingView.loupeViewPosition {
            let location = gesture.location(in: trackingView)
            let loupeRadius = trackingView.loupeSize / 2
            let distance = hypot(location.x - loupeViewPos.x, location.y - loupeViewPos.y)
            if distance <= loupeRadius {
                switch gesture.state {
                case .began:
                    initialMagnification = trackingView.loupeMagnification
                case .changed:
                    let newMag = initialMagnification * (1 + gesture.magnification)
                    let clampedMag = max(0.25, min(20.0, newMag))
                    trackingView.loupeMagnification = clampedMag
                    trackingView.onLoupeMagnificationChanged?(clampedMag)
                    trackingView.needsDisplay = true
                default:
                    break
                }
                return
            }
        }

        // Not over loupe — forward the pinch to the scroll view.
        // NSScrollView's built-in magnification would normally do this, but
        // our custom recognizer captures the event first and without forwarding,
        // the scroll view never zooms (#562).
        guard let scrollView = scrollView else { return }
        switch gesture.state {
        case .began:
            isUserMagnifying = true
            // A pinch hands zoom control to the user (#4279).
            markManualZoom()
            initialMagnification = scrollView.magnification
        case .changed:
            let newMag = initialMagnification * (1 + gesture.magnification)
            let clamped = max(scrollView.minMagnification, min(scrollView.maxMagnification, newMag))
            // Set magnification centred on the gesture location so the pinch
            // feels anchored under the cursor.
            let location = gesture.location(in: scrollView.contentView)
            scrollView.setMagnification(clamped, centeredAt: location)
        case .ended, .cancelled, .failed:
            // Snap to fit when the pinch lands NEAR fit (Daniel, 2026-08-21:
            // "when we zoom out it should get to full image and snap to
            // that, without going too far. we can keep going if we want").
            // A ±15% band: inside it the intent was clearly "show me the
            // whole page", so land exactly there; a pinch past the band is
            // the user deliberately going further and is left alone.
            if let fit = calculateFitScale(),
               abs(scrollView.magnification - fit) / fit < 0.15 {
                scrollView.magnification = fit
            }
            // #596: write the final magnification back to the @Binding
            // so the next updateNSView sync-check sees matching values
            // and doesn't snap the zoom back to the pre-pinch scale.
            //
            // #748: ORDER MATTERS. Setting `isUserMagnifying = false`
            // synchronously before `onScaleChanged` runs lets SwiftUI
            // fire `updateNSView` in the gap before the Task @MainActor
            // queued inside `onScaleChanged` writes the binding. That
            // updateNSView sees `scale` still at the pre-pinch value
            // and reverts magnification — the user sees a ~250ms flash
            // to the old zoom. Defer the gate-reopen until after the
            // binding write has had a chance to propagate.
            onScaleChanged?(scrollView.magnification)
            Task { @MainActor [weak self] in
                // Yield once so the binding-write task scheduled inside
                // `onScaleChanged` runs first (Swift Concurrency
                // preserves FIFO order on the main actor; yielding
                // makes that explicit and survives priority changes).
                await Task.yield()
                self?.isUserMagnifying = false
            }
        default:
            break
        }
    }
}
#endif
