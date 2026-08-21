#if os(macOS)
import SwiftUI

extension ZoomableImagePreview {
    // MARK: - Event Handlers

    func handleImageURLChanged() async {
        if let renderedImage {
            image = renderedImage
            imageSize = renderedImage.size
            return
        }
        guard let url else { image = nil; return }
        let cgImage = await decodeSDRCGImage(from: url)
        guard !Task.isCancelled else { return }
        if let cgImage {
            let decoded = NSImage(cgImage: cgImage, size: NSSize(width: cgImage.width, height: cgImage.height))
            image = decoded
            imageSize = decoded.size
        } else {
            Self.logger.error("Failed to load NSImage from: \(url.path)")
        }
    }

    func handleViewAppeared() {
        // #4279: no persisted per-document zoom is restored here any more. A
        // preview always opens at fit-to-view (`PreviewInitialZoomPolicy`), the
        // way Preview.app does; restoring a scale saved from an earlier, smaller
        // pane is exactly what made previews open at half the pane.
        loadAnnotations()
    }

    func handleDocumentIDChanged() {
        isDrawingRegion = false
        loadAnnotations()
    }

    func handleRenderedImageChanged(_ newImg: NSImage?) {
        if let img = newImg {
            image = img
            imageSize = img.size
        }
    }

    func handleScaleChanged(_ newScale: CGFloat) {
        // Fetch full-res source on first zoom past 1.5× (#2427). The display
        // image is JPEG-compressed for fast loading; once zoomed the source file
        // provides the real pixel detail. Only fires once per document.
        //
        // NOT while a rendition is on screen (2026-08-20 bbox review, D2).
        // `getSourceData` returns the ORIGINAL file, so in editor /
        // backend-rendered mode this swapped the enhanced, cropped, rotated or
        // split image the user was looking at for the raw source the moment
        // they zoomed past 1.5×. Different pixels, and for every frame-changing
        // rendition a different aspect ratio — which renormalizes `imageSize`
        // and moves every bounding box on the page. The zoom-triggered upgrade
        // is only ever valid for the plain-preview path, where what is drawn
        // already IS the source.
        guard renderedImage == nil else { return }
        if newScale > 1.5, highResImage == nil, !isLoadingHighRes, let docId = documentId {
            isLoadingHighRes = true
            Task {
                do {
                    let data = try await storageService.getSourceData(docId)
                    if let img = NSImage(data: data) {
                        highResImage = img
                        image = img
                        imageSize = img.size
                    } else {
                        // Decodable bytes that aren't an image is a real
                        // failure, not "no upgrade available".
                        Self.logger.error(
                            "High-res source for \(docId) could not be decoded as an image"
                        )
                    }
                } catch {
                    // Never swallowed (#absence-read-as-success): a failed
                    // upgrade leaves the reader zoomed into a soft preview,
                    // and a silent `try?` made that indistinguishable from a
                    // source that simply has no more detail to give.
                    Self.logger.error(
                        "High-res source fetch failed for \(docId): \(String(describing: error))"
                    )
                }
                isLoadingHighRes = false
            }
        }
    }

    func handleDocumentIDChangedForHighRes() {
        highResImage = nil
        isLoadingHighRes = false
    }

    func handleMagnifierLockChanged(_ wasLocked: Bool, _ isLocked: Bool) {
        if isLocked && !wasLocked {
            lockedPosition = cursorPosition
        }
    }
}

#endif
