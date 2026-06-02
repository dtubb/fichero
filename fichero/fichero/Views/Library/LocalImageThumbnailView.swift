import AppKit
import SwiftUI

/// Renders a local image-file thumbnail, decoding off the main thread with a
/// small in-memory cache. Mirrors `PDFThumbnailView`'s load pattern so library
/// list/grid scrolling never blocks the main thread on
/// `NSImage(contentsOfFile:)`. (#1509)
///
/// On decode failure (missing or dead path) it falls back to the backend
/// thumbnail — preserving the spirit of the previous
/// `let nsImage = NSImage(...)` fall-through, while keeping #1458's rule that
/// image docs never show their OCR text as a thumbnail.
struct LocalImageThumbnailView: View {
    let path: String
    let documentId: String
    var contentMode: ContentMode = .fill

    @State private var image: NSImage?
    @State private var didFail = false

    var body: some View {
        Group {
            if let image {
                Image(nsImage: image)
                    .resizable()
                    .aspectRatio(contentMode: contentMode)
            } else if didFail {
                // Local file gone — use the backend-generated thumbnail.
                LibraryImageView(documentId: documentId, imageType: .thumbnail)
                    .aspectRatio(contentMode: contentMode)
            } else {
                // Neutral placeholder while the off-main decode runs.
                Color(.windowBackgroundColor)
            }
        }
        .task(id: path) {
            if let cached = LocalImageThumbnailCache.shared.image(forKey: path) {
                image = cached
                return
            }
            let loaded = await Task.detached(priority: .userInitiated) {
                NSImage(contentsOfFile: path)
            }.value
            if let loaded {
                LocalImageThumbnailCache.shared.set(loaded, forKey: path)
                image = loaded
            } else {
                didFail = true
            }
        }
    }
}

/// Process-wide decoded-thumbnail cache keyed by file path. `NSCache` evicts
/// automatically under memory pressure, so this never grows unbounded.
/// `@unchecked Sendable`: `NSCache` is documented thread-safe but isn't
/// annotated `Sendable` by Foundation, so we vouch for it explicitly.
final class LocalImageThumbnailCache: @unchecked Sendable {
    static let shared = LocalImageThumbnailCache()
    private let cache = NSCache<NSString, NSImage>()

    private init() {
        cache.countLimit = 512
    }

    func image(forKey key: String) -> NSImage? {
        cache.object(forKey: key as NSString)
    }

    func set(_ image: NSImage, forKey key: String) {
        cache.setObject(image, forKey: key as NSString)
    }
}
