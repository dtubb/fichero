#if os(macOS)
import SwiftUI

extension ZoomableImagePreview {
    // MARK: - Persisted per-document zoom scale
    // (Moved from the main struct body to stay under type-body-length.)

    func loadSavedScale(for key: String) -> CGFloat? {
        guard let data = zoomScalesByDocumentJSON.data(using: .utf8),
              let values = try? JSONDecoder().decode([String: Double].self, from: data),
              let saved = values[key],
              saved > 0 else {
            return nil
        }
        return CGFloat(saved)
    }

    func saveScale(_ newScale: CGFloat, for key: String) {
        var values: [String: Double] = [:]
        if let data = zoomScalesByDocumentJSON.data(using: .utf8),
           let decoded = try? JSONDecoder().decode([String: Double].self, from: data) {
            values = decoded
        }
        values[key] = Double(newScale)
        if let encoded = try? JSONEncoder().encode(values),
           let json = String(data: encoded, encoding: .utf8) {
            zoomScalesByDocumentJSON = json
        }
    }

    // MARK: - Zoom Actions

    func zoomIn() {
        withAnimation(.easeInOut(duration: 0.2)) {
            scale = min(scale * 1.25, maxScale)
        }
    }

    func zoomOut() {
        withAnimation(.easeInOut(duration: 0.2)) {
            scale = max(scale / 1.25, minScale)
        }
    }

    func fitToWindow() {
        if let fitScale = imageCoordinator?.calculateFitScale() {
            scale = fitScale
            // Defer center to next run loop so magnification has applied
            DispatchQueue.main.async {
                imageCoordinator?.centerContent()
            }
        }
    }

    func actualSize() {
        // #599: pixel 1:1 — one image pixel per display point. Setting
        // `scale = 1.0` (NSScrollView.magnification = 1.0) shows the image
        // at NSImage.size, which on TIFF files with DPI metadata is
        // *smaller* than the actual pixel dimensions — a 300 DPI TIFF at
        // 1200×900 pixels reports `size == 288×216 points`, so
        // magnification=1.0 shrinks the image to DPI-logical size, not
        // actual pixels. The ratio of pixelsWide to size.width gives the
        // magnification that maps one image pixel to one display point,
        // matching Preview.app's Actual Size / ⌘⌥0 behaviour on macOS.
        // Falls back to 1.0 if the image has no representations (vector
        // or corrupt TIFF) or if pixel ratio exceeds the current clamp
        // — maxScale=10 is a reasonable ceiling for a UI affordance.
        let pixelRatio: CGFloat
        if let image,
           let rep = image.representations.first,
           image.size.width > 0 {
            pixelRatio = CGFloat(rep.pixelsWide) / image.size.width
        } else {
            pixelRatio = 1.0
        }
        scale = min(max(pixelRatio, minScale), maxScale)
        DispatchQueue.main.async {
            imageCoordinator?.centerContent()
        }
    }

    func panLeft() {
        panBy(deltaX: -80, deltaY: 0)
    }

    func panRight() {
        panBy(deltaX: 80, deltaY: 0)
    }

    func panUp() {
        panBy(deltaX: 0, deltaY: 80)
    }

    func panDown() {
        panBy(deltaX: 0, deltaY: -80)
    }

    func panBy(deltaX: CGFloat, deltaY: CGFloat) {
        imageCoordinator?.panBy(
            x: deltaX / max(scale, 0.01),
            y: deltaY / max(scale, 0.01)
        )
    }
}

#endif
