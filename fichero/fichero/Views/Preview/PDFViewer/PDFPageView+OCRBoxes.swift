import PDFKit
import SwiftUI

#if canImport(AppKit)
import AppKit
import OSLog

/// File-scoped: `PDFPageWithToolbar.log` is `private`, so it is not visible
/// here, and reaching for it would only widen that type's surface.
private let ocrBoxesLogger = Logger(subsystem: "app.fichero.fichero", category: "OCRBoxes")

// Split out of PDFPageView.swift (#4418): that file is at its 1000-line budget
// and its Coordinator at the 250-line type budget, so the renderer lives beside
// it rather than pushing both over.
extension PDFPageView.Coordinator {
    /// Draw the page's recognised text regions as outline annotations (#4418).
    ///
    /// PDFs already carry this geometry — the importer reads the text layer
    /// on every import — and until now nothing rendered it, because
    /// `OCRGeometryOverlay` is a SwiftUI view that lays out as a sibling of
    /// an `Image`. `PDFView` is an AppKit view owning its own scroll, zoom
    /// and page layout, so there is no shared space to put that overlay in.
    /// Annotations are how this surface draws, exactly as `applyRegions`
    /// above and the #2105/#3449 claim-source highlight already do.
    ///
    /// The coordinate conversion is NOT new: `OCRGeometryBox.bbox` is the
    /// same normalised top-left `[x, y, w, h]` array that
    /// `PDFRegionGeometry.pageRect` already flips into PDFKit's bottom-left
    /// page space for user-drawn regions.
    ///
    /// `.cropBox`, not the `.mediaBox` `applyRegions` uses: these boxes are
    /// normalised by the importer against PyMuPDF's `page.rect`, which
    /// derives from the CropBox. The two differ only on pages whose crop is
    /// inset from the media box, and on those the crop is the right basis.
    /// User-drawn regions stay on mediaBox because they were normalised
    /// against it — each stays consistent with its own producer.
    ///
    /// Its own `userName` keeps it disjoint from the region and
    /// claim-source sweeps, so the three never clear each other.
    func applyOCRBoxes(to view: PDFView) {
        guard let page = view.currentPage else { return }
        for existing in page.annotations where existing.userName == Self.ocrBoxAnnotationName {
            page.removeAnnotation(existing)
        }
        // `ocrBoxes` arrives already reduced to ONE level by the owner (words
        // when the pass produced them, lines otherwise). Drawing every level
        // would nest a line box around each of its own word boxes, which reads
        // as clutter rather than structure and carpets a dense page.
        guard !owner.ocrBoxes.isEmpty else { return }
        let cropBounds = page.bounds(for: .cropBox)
        for box in owner.ocrBoxes {
            guard let rect = PDFRegionGeometry.pageRect(normalized: box.bbox, pageSize: cropBounds.size)
            else { continue }
            // `pageRect` performs the flip but computes from the SIZE alone, so
            // it assumes a zero origin. That holds for `applyRegions`, which
            // uses the mediaBox, but a cropBox can be INSET — and then every
            // box is displaced by the crop's offset. The claim-source highlight
            // (#2105/#3449) re-adds `cropBounds.minX/minY` for exactly this
            // reason; doing the same here keeps the two paths in agreement.
            let placed = rect.offsetBy(dx: cropBounds.minX, dy: cropBounds.minY)
            let annotation = PDFAnnotation(bounds: placed, forType: .square, withProperties: nil)
            // Outline only. A filled box would obscure the very glyphs it
            // is describing, and these exist to be read against.
            annotation.color = NSColor.systemTeal
            annotation.userName = Self.ocrBoxAnnotationName
            page.addAnnotation(annotation)
        }
    }

    static let ocrBoxAnnotationName = "fichero.ocr-box"
}

// The loader lives here beside the renderer, and out of PDFPageWithToolbar,
// whose body is deliberately kept small so no sub-expression trips the Swift
// type-checker timeout (the LibraryWindow.body failure mode).
extension PDFPageWithToolbar {
    /// Fetch this page's recognised text regions (#4418).
    ///
    /// The artifact choice is `OCRGeometrySelection.load` — the SAME decision
    /// the image preview makes. Only the drawing differs between the two
    /// surfaces, because AppKit's `PDFView` has no coordinate space a SwiftUI
    /// overlay can lay out in; which artifact wins must not differ.
    func loadOCRGeometry() async {
        ocrGeometry = nil
        guard ocrBoxesEnabled, let artifactService else { return }
        do {
            ocrGeometry = try await OCRGeometrySelection.load(
                documentId: effectiveDocumentId,
                using: artifactService
            )
        } catch {
            // Render nothing and say so in the log rather than silently — no
            // boxes must not be indistinguishable from a failed fetch (#4418).
            ocrBoxesLogger.error(
                "OCR geometry load failed for \(effectiveDocumentId): \(String(describing: error))"
            )
        }
    }
}
#endif
