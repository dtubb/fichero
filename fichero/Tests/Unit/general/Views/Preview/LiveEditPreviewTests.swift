#if canImport(AppKit)
import AppKit
#elseif canImport(UIKit)
import UIKit
#endif
@testable import Fichero
import CoreGraphics
import Foundation
import Testing

/// Client-side Core Image live preview (#3673): composites in-progress slider
/// values over the original with NO backend, and the model resyncs to the
/// server frame on commit (ImageEditChain stays the sole source of truth).
@MainActor
@Suite("LiveEditPreview")
struct LiveEditPreviewTests {

    /// A small solid-colour bitmap, wrapped as the platform image type.
    private static func testImage(_ side: Int = 8) -> PlatformImage {
        let space = CGColorSpaceCreateDeviceRGB()
        let context = CGContext(
            data: nil, width: side, height: side, bitsPerComponent: 8, bytesPerRow: 0,
            space: space, bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
        )!
        context.setFillColor(CGColor(red: 0.5, green: 0.5, blue: 0.5, alpha: 1))
        context.fill(CGRect(x: 0, y: 0, width: side, height: side))
        let cgImage = context.makeImage()!
        #if canImport(AppKit)
        return NSImage(cgImage: cgImage, size: NSSize(width: side, height: side))
        #else
        return UIImage(cgImage: cgImage)
        #endif
    }

    @Test("composites a frame for given slider values, with no backend call")
    func rendersCompositedFrame() {
        let live = LiveEditPreview(original: Self.testImage())
        #expect(live != nil)

        let frame = live?.render(brightness: 1.5, contrast: 1.2, sharpen: 1.3, angleDegrees: 0)
        #expect(frame != nil)
        #expect(frame?.pixelSize.width ?? 0 > 0)
        #expect(frame?.pixelSize.height ?? 0 > 0)
    }

    @Test("neutral values still return a valid frame")
    func neutralRenders() {
        let frame = LiveEditPreview(original: Self.testImage())?
            .render(brightness: 1, contrast: 1, sharpen: 1, angleDegrees: 0)
        #expect(frame != nil)
    }

    @Test("model: live edit sets a provisional frame, discard resyncs to the server preview")
    func liveEditThenDiscardResyncs() {
        let model = ImageEditorModel()
        let original = PreviewImage(image: Self.testImage(), pixelSize: CGSize(width: 8, height: 8))
        let edited = PreviewImage(image: Self.testImage(), pixelSize: CGSize(width: 8, height: 8))
        model.originalPreview = original
        model.editedPreview = edited
        model.showEdited = true
        model.preview = edited

        model.previewLiveEdit(brightness: 1.6, contrast: 1, sharpen: 1)
        // A provisional Core Image frame replaced the server preview...
        #expect(model.preview?.image !== edited.image)

        model.discardLiveEdit()
        // ...and discarding restores the authoritative (server) edited preview.
        #expect(model.preview?.image === edited.image)
    }
}
