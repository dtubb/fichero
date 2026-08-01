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
        guard !owner.ocrBoxes.isEmpty else { return }
        let pageSize = page.bounds(for: .cropBox).size
        for box in owner.ocrBoxes {
            guard let rect = PDFRegionGeometry.pageRect(normalized: box.bbox, pageSize: pageSize)
            else { continue }
            let annotation = PDFAnnotation(bounds: rect, forType: .square, withProperties: nil)
            // Outline only. A filled box would obscure the very glyphs it
            // is describing, and these exist to be read against.
            annotation.color = NSColor.systemTeal
            annotation.userName = Self.ocrBoxAnnotationName
            page.addAnnotation(annotation)
        }
    }

    static let ocrBoxAnnotationName = "fichero.ocr-box"
}
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
