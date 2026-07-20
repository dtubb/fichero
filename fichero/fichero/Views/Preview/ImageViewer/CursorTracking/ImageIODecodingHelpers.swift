#if canImport(UIKit)
import CoreImage
import ImageIO
import UIKit

/// Decode `url` to a `Sendable` `CGImage` (+ its EXIF orientation) OFF the main
/// thread (#3864), so a large scan no longer decodes inside makeUIView/updateUIView.
/// The caller wraps it in a `UIImage` on the main actor, preserving orientation via
/// `UIImage(cgImage:scale:orientation:)` (UIImage would otherwise apply it for us,
/// but a bare `CGImage` carries none).
func decodeCGImage(from url: URL) async -> (cgImage: CGImage, orientation: UIImage.Orientation)? {
    await Task.detached(priority: .userInitiated) {
        guard let source = CGImageSourceCreateWithURL(url as CFURL, nil),
              let cgImage = CGImageSourceCreateImageAtIndex(
                source, 0, [kCGImageSourceShouldCache: true] as CFDictionary
              ) else { return nil }
        let props = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any]
        let raw = (props?[kCGImagePropertyOrientation] as? UInt32) ?? 1
        return (cgImage, uiImageOrientation(fromEXIF: raw))
    }.value
}

/// Map an EXIF/`CGImagePropertyOrientation` raw value to the matching (same-named)
/// `UIImage.Orientation`. The frameworks name the same physical orientations
/// identically even though their raw values differ.
func uiImageOrientation(fromEXIF raw: UInt32) -> UIImage.Orientation {
    switch CGImagePropertyOrientation(rawValue: raw) ?? .up {
    case .up: return .up
    case .upMirrored: return .upMirrored
    case .down: return .down
    case .downMirrored: return .downMirrored
    case .left: return .left
    case .leftMirrored: return .leftMirrored
    case .right: return .right
    case .rightMirrored: return .rightMirrored
    @unknown default: return .up
    }
}
#endif
