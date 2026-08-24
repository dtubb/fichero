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
        linkedSelectionBoxes = []
        loadAnnotations()
        // S6: the NEXT image fits whole (zoom-to-fit, both axes) — stepping
        // siblings at the previous zoom left tall items overflowing.
        pendingFitOnNextImage = true
    }

    func handleRenderedImageChanged(_ newImg: NSImage?) {
        if let img = newImg {
            image = img
            imageSize = img.size
            if pendingFitOnNextImage {
                pendingFitOnNextImage = false
                // Async: the scroll view needs the new documentView bounds
                // before the fit math sees them.
                DispatchQueue.main.async { fitToWindow() }
            }
            // Boxes survive a page step (Daniel, 2026-08-21: "they should
            // still be shown on the next page — you have to click to hide
            // and show them again"): the geometry fetch racing the sibling
            // swap can lose; once the new page's pixels are up, a missing
            // geometry gets ONE reload rather than waiting for the toggle.
            if ocrBoxesEnabled, ocrGeometry == nil {
                Task { await loadOCRGeometry() }
            }
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

    /// Reader → preview word linking (Daniel, 2026-08-23): the reader's text
    /// selection arrives as char offsets; intersect with this page's word
    /// geometry and light the words. Cleared selection, another document's
    /// selection, or a geometry set measured on a different frame all clear —
    /// stale word lights are the same lie as a stale highlight band.
    func handleReaderTextSelection(_ note: Notification) {
        guard let geometry = ocrGeometry,
              geometryFrameMatchesDisplay(geometry),
              let docId = note.userInfo?["documentId"] as? String,
              let start = note.userInfo?["charStart"] as? Int,
              let end = note.userInfo?["charEnd"] as? Int else {
            if !linkedSelectionBoxes.isEmpty { linkedSelectionBoxes = [] }
            return
        }
        if docId == documentId {
            linkedSelectionBoxes = wordBoxes(intersecting: start..<end, in: geometry)
            return
        }
        // Different document: the reader usually shows an ENTRY while this
        // preview shows its source PAGE. The selection's TEXT anchors it in
        // the page's own transcript; unfindable text clears rather than
        // guesses.
        if let text = note.userInfo?["text"] as? String,
           let range = geometryRange(of: text, in: geometry.text) {
            linkedSelectionBoxes = wordBoxes(intersecting: range, in: geometry)
        } else if !linkedSelectionBoxes.isEmpty {
            linkedSelectionBoxes = []
        }
    }
}

#endif
