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
        if let key = scaleKey {
            if let saved = loadSavedScale(for: key) {
                scale = saved
            }
        }
        loadAnnotations()
    }

    func handleDocumentIDChanged() {
        isDrawingRegion = false
        loadAnnotations()
    }

    func handleURLChanged() {
        if let key = scaleKey, let saved = loadSavedScale(for: key) {
            scale = saved
        }
    }

    func handleRenderedImageChanged(_ newImg: NSImage?) {
        if let img = newImg {
            image = img
            imageSize = img.size
        }
    }

    func handleScaleChanged(_ newScale: CGFloat) {
        if let key = scaleKey {
            saveScale(newScale, for: key)
        }
        // Fetch full-res source on first zoom past 1.5× (#2427). The display
        // image is JPEG-compressed for fast loading; once zoomed the source file
        // provides the real pixel detail. Only fires once per document.
        if newScale > 1.5, highResImage == nil, !isLoadingHighRes, let docId = documentId {
            isLoadingHighRes = true
            Task {
                if let data = try? await storageService.getSourceData(docId),
                   let img = NSImage(data: data) {
                    highResImage = img
                    image = img
                    imageSize = img.size
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
