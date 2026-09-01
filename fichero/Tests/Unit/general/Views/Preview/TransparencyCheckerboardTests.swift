#if canImport(AppKit)
import AppKit
import Testing

@testable import Fichero

/// A background-removed PNG gets a PLAIN WHITE ground under the image's own
/// frame (Daniel, 2026-09-01: "when transparent, I say just white" — the
/// checkerboard this suite used to pin made a cleaned page look like a
/// defect). The ground is drawn ONLY when the image carries an alpha channel;
/// an opaque page is untouched.
@MainActor
struct TransparencyCheckerboardTests {
    private func renderedPixels(image: NSImage) -> [UInt8] {
        let view = TrackingImageView(frame: NSRect(x: 0, y: 0, width: 32, height: 32))
        view.imageScaling = .scaleNone
        view.image = image
        guard let rep = view.bitmapImageRepForCachingDisplay(in: view.bounds) else { return [] }
        view.cacheDisplay(in: view.bounds, to: rep)
        var reds: [UInt8] = []
        for y in 0..<rep.pixelsHigh where y % 4 == 0 {
            for x in 0..<rep.pixelsWide where x % 4 == 0 {
                if let color = rep.colorAt(x: x, y: y), color.alphaComponent > 0 {
                    reds.append(UInt8(max(0, min(255, color.redComponent * 255))))
                }
            }
        }
        return reds
    }

    /// A real RGBA bitmap, not a drawing-handler image: the production
    /// detection keys on `representations.hasAlpha`, which an NSCustomImageRep
    /// (what the drawing-handler initializer produces) does not report — the
    /// viewer's real inputs are decoded bitmap reps, so the fixture must be one.
    private func solidImage(white: CGFloat, alpha: CGFloat) -> NSImage {
        let rep = NSBitmapImageRep(
            bitmapDataPlanes: nil, pixelsWide: 32, pixelsHigh: 32,
            bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true,
            isPlanar: false, colorSpaceName: .deviceRGB,
            bytesPerRow: 0, bitsPerPixel: 0
        )!
        NSGraphicsContext.saveGraphicsState()
        NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
        // .copy, not sourceOver: writes the EXACT rgba including alpha 0 —
        // fresh bitmap memory is not guaranteed zeroed.
        NSColor(white: white, alpha: alpha).setFill()
        NSRect(x: 0, y: 0, width: 32, height: 32).fill(using: .copy)
        NSGraphicsContext.restoreGraphicsState()
        let image = NSImage(size: NSSize(width: 32, height: 32))
        image.addRepresentation(rep)
        return image
    }

    @Test func transparentImageGetsWhiteGround() {
        // Fully transparent pixels: whatever shows through is the ground. A
        // ground that was drawn yields opaque samples; every one is white.
        let reds = renderedPixels(image: solidImage(white: 1, alpha: 0))
        #expect(!reds.isEmpty, "no ground was drawn under a transparent image")
        #expect(reds.allSatisfy { $0 > 245 }, "the ground must be plain white, never a checker")
    }

    @Test func opaqueImageGetsNoChecker() {
        let reds = renderedPixels(image: solidImage(white: 1, alpha: 1))
        #expect(!reds.isEmpty)
        #expect(reds.allSatisfy { $0 > 245 })
    }
}
#endif
