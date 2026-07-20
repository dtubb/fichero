#if canImport(AppKit)
import AppKit
import CoreImage
import ImageIO

/// Load an image decoded to SDR so iPhone HEIC HDR gain maps don't elevate
/// the window's EDR headroom and wash out surrounding UI. Setting
/// `preferredImageDynamicRange = .standard` on NSImageView alone isn't
/// sufficient — if the NSImage carries an HDR representation the system
/// still raises headroom. Decoding via ImageIO with
/// `kCGImageSourceDecodeRequest = kCGImageSourceDecodeToSDR` (macOS 14+)
/// strips the HDR payload at load time.
///
/// We also apply the EXIF `Orientation` tag manually — `NSImage(contentsOf:)`
/// does this automatically via its representation system, but the ImageIO
/// path returns raw pixels. Without the manual rotate, iPhone photos taken
/// in portrait or upside-down come in sideways.
/// The SDR + orientation-corrected decode, off the main thread (#3864). Returns a
/// `Sendable` `CGImage` (safe to construct off the main actor and cross back); the
/// caller wraps it in an `NSImage` on the main actor. A 40MP scan decodes on a
/// background executor so opening a preview / flipping pages no longer blocks the
/// main thread inside `makeNSView` / `updateNSView`. Mirrors the `Task.detached`
/// pattern in `StorageService.decodeImage`.
/// Internal so the sibling `ImageViewerComponents` overview image reuses this exact
/// SDR + orientation decode (same off-main path, matching orientation).
func decodeSDRCGImage(from url: URL) async -> CGImage? {
    await Task.detached(priority: .userInitiated) {
        guard let source = CGImageSourceCreateWithURL(url as CFURL, nil) else { return nil }
        let options: [CFString: Any] = [
            kCGImageSourceDecodeRequest: kCGImageSourceDecodeToSDR,
            kCGImageSourceShouldCache: true
        ]
        guard let cgImage = CGImageSourceCreateImageAtIndex(source, 0, options as CFDictionary) else {
            return nil
        }
        let props = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any]
        let orientationRaw = (props?[kCGImagePropertyOrientation] as? UInt32) ?? 1
        let orientation = CGImagePropertyOrientation(rawValue: orientationRaw) ?? .up
        guard orientation != .up else { return cgImage }
        let oriented = CIImage(cgImage: cgImage).oriented(orientation)
        let ctx = CIContext(options: nil)
        return ctx.createCGImage(oriented, from: oriented.extent) ?? cgImage
    }.value
}
#endif
