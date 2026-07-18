#if canImport(AppKit)
import AppKit
#elseif canImport(UIKit)
import UIKit
#endif
import CoreImage
import CoreImage.CIFilterBuiltins
import Foundation

/// Client-side Core Image live preview for continuously-dragged image-edit
/// sliders (#3673 — the client half of the hybrid #3213). Composites the
/// ALREADY-FETCHED original image with the in-progress slider values through a
/// GPU `CIContext` — with NO backend call — so brightness/contrast/sharpen/
/// rotate-angle preview at ~60fps with no network chatter.
///
/// This is a LATENCY OPTIMISATION ONLY, never a source of truth. The frame it
/// produces is PROVISIONAL: on slider release the editor POSTs the op, the engine
/// appends it to the `ImageEditChain` (the sole source of truth), and the server
/// bytes replace this frame — so the two can't diverge more than one round-trip.
/// The values are the editor's 1.0-neutral multipliers; the mapping onto Core
/// Image's parameters is approximate on purpose — exactness comes from the server
/// resync, not this frame. Cross-platform (Core Image is AppKit/UIKit).
struct LiveEditPreview {
    private let source: CIImage
    private let context: CIContext

    /// Build from the original preview's decoded image, captured once. Callers
    /// evict + rebuild on document change / chain reset. Returns nil if the image
    /// has no backing `CGImage`.
    init?(original: PlatformImage) {
        guard let cgImage = original.liveEditCGImage else { return nil }
        self.source = CIImage(cgImage: cgImage)
        self.context = CIContext(options: [.useSoftwareRenderer: false])
    }

    /// Composite the ABSOLUTE slider values over the fixed original (never
    /// compounding between frames). All-neutral (1.0 / 0°) returns the original.
    func render(
        brightness: Double = 1,
        contrast: Double = 1,
        sharpen: Double = 1,
        angleDegrees: Double = 0
    ) -> PreviewImage? {
        var image = source

        // colorControls: the editor's brightness is a 1.0-neutral MULTIPLIER;
        // Core Image's inputBrightness is ADDITIVE (0 neutral), so shift by -1.
        // Contrast maps ~directly (1.0 neutral on both sides).
        if brightness != 1.0 || contrast != 1.0 {
            let filter = CIFilter.colorControls()
            filter.inputImage = image
            filter.brightness = Float(brightness - 1.0)
            filter.contrast = Float(contrast)
            filter.saturation = 1.0
            if let output = filter.outputImage { image = output }
        }

        // sharpen: editor 1.0 neutral → 0 sharpness; > 1.0 sharpens.
        if sharpen > 1.0 {
            let filter = CIFilter.sharpenLuminance()
            filter.inputImage = image
            filter.sharpness = Float(sharpen - 1.0)
            if let output = filter.outputImage { image = output }
        }

        // rotate-angle: straightenFilter rotates about the centre (radians) and
        // crops to fill, matching the editor's straighten/rotate-angle slider.
        if angleDegrees != 0 {
            let filter = CIFilter.straighten()
            filter.inputImage = image
            filter.angle = Float(angleDegrees * .pi / 180)
            if let output = filter.outputImage { image = output }
        }

        guard let cgImage = context.createCGImage(image, from: image.extent) else { return nil }
        let pixelSize = CGSize(width: cgImage.width, height: cgImage.height)
        #if canImport(AppKit)
        return PreviewImage(
            image: NSImage(cgImage: cgImage, size: NSSize(width: cgImage.width, height: cgImage.height)),
            pixelSize: pixelSize
        )
        #elseif canImport(UIKit)
        return PreviewImage(image: UIImage(cgImage: cgImage), pixelSize: pixelSize)
        #endif
    }
}

private extension PlatformImage {
    /// The backing `CGImage`, cross-platform.
    var liveEditCGImage: CGImage? {
        #if canImport(AppKit)
        return cgImage(forProposedRect: nil, context: nil, hints: nil)
        #elseif canImport(UIKit)
        return cgImage
        #endif
    }
}
