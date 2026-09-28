#if canImport(AppKit)
import AppKit

extension ImageWithCursorTrackingMacCoordinator {
    /// Mount the document overlay inside the image view once, keep it on the image's own rect, and
    /// hand it what to draw (#5020, #5142). Called from `updateNSView`: the overlay view redraws
    /// only when what it draws changed, and scrolling never calls this at all -- AppKit moves it.
    @MainActor
    func syncDocumentOverlay(_ overlay: DocumentOverlay, in imageView: TrackingImageView) {
        let view: DocumentOverlayView
        if let existing = documentOverlayView, existing.superview === imageView {
            view = existing
        } else {
            // It FILLS the image view and follows its frame (the view is enlarged and the image
            // centred when zoomed out below fit); where the image sits is read at draw time, so
            // the two can never be a frame apart.
            view = DocumentOverlayView(frame: imageView.bounds)
            view.autoresizingMask = [.width, .height]
            imageView.addSubview(view)
            documentOverlayView = view
        }
        view.overlay = overlay
    }
}
#endif
