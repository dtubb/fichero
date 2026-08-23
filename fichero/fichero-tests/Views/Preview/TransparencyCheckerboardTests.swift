#if canImport(AppKit)
import AppKit
import Testing

@testable import Fichero

/// A background-removed PNG must READ as transparent in the viewer — the bug
/// was alpha rendering over a near-white pane ground, indistinguishable from
/// a white background. TrackingImageView now draws a checkerboard under the
/// image, but ONLY when the image actually carries an alpha channel.
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

    private func solidImage(white: CGFloat, alpha: CGFloat) -> NSImage {
        NSImage(size: NSSize(width: 32, height: 32), flipped: false) { rect in
            NSColor(white: white, alpha: alpha).setFill()
            rect.fill()
            return true
        }
    }

    @Test func transparentImageGetsCheckerGround() {
        // Fully transparent pixels: whatever shows through is the checker.
        let reds = renderedPixels(image: solidImage(white: 1, alpha: 0))
        // The darker checker square is 0.78 grey (~199); pure white is 255.
        // Its presence proves the ground was drawn.
        #expect(reds.contains { (170...230).contains($0) })
    }

    @Test func opaqueImageGetsNoChecker() {
        let reds = renderedPixels(image: solidImage(white: 1, alpha: 1))
        #expect(!reds.isEmpty)
        #expect(reds.allSatisfy { $0 > 245 })
    }
}
#endif
