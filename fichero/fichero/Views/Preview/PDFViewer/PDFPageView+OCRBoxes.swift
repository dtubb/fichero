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
        (view as? PinchOwningPDFView)?.segmentBoxes = Self.segmentBoxes(
            owner.ocrBoxes, on: page, selectedId: owner.segmentEditing.selected?.box.segmentId
        )
        (view as? PinchOwningPDFView)?.segmentPageId = owner.segmentEditing.pageDocumentId
        // `ocrBoxes` arrives already reduced to ONE level by the owner (words
        // when the pass produced them, lines otherwise). Drawing every level
        // would nest a line box around each of its own word boxes, which reads
        // as clutter rather than structure and carpets a dense page.
        guard !owner.ocrBoxes.isEmpty else { return }
        let cropBounds = page.bounds(for: .cropBox)
        // `bounds(for:)` and every `PDFAnnotation` are UNROTATED page space —
        // "you might need to transform the points if the page has a rotation
        // on it" — while the engine normalises PDF text geometry in DISPLAY
        // space, the picture the reader is actually looking at and the frame
        // every server-rendered rendition shares. On a `/Rotate 90` page,
        // handing the box straight to an annotation drew it ninety degrees out
        // of true, sideways across the text it describes.
        let rotation = page.rotation
        for box in owner.ocrBoxes {
            // A segment with its own shapes is drawn AS them -- outline, baseline, points -- as on an image.
            if let shaped = PDFShapeAnnotations.make(for: box, on: page, userName: Self.ocrBoxAnnotationName) {
                shaped.forEach(page.addAnnotation)
                continue
            }
            let pageSpaceBox = PDFRegionGeometry.unrotated(normalized: box.bbox, rotation: rotation)
            guard let rect = PDFRegionGeometry.pageRect(normalized: pageSpaceBox, pageSize: cropBounds.size)
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
            //
            // …and how sure the machine is about WHERE the word is shows here
            // too (2026-09-04). The image overlay and this one draw the same
            // geometry; a box that reads as a guess on one surface and as an
            // assertion on the other is the two disagreeing about the same
            // fact. PDFKit gives a border its own dash style, so the axis is
            // spelled the same way: recessive colour plus a dash.
            // A box with no reading is dashed the same way (`SegmentsPane.lacksReading`).
            let uncertain = OCRBoxConfidence.isUncertain(box) || box.noReading
            annotation.color = uncertain
                ? NSColor.systemTeal.withAlphaComponent(0.35)
                : NSColor.systemTeal
            if uncertain {
                let border = PDFBorder()
                border.lineWidth = 1
                border.style = .dashed
                border.dashPattern = [3, 2]
                annotation.border = border
            }
            annotation.userName = Self.ocrBoxAnnotationName
            page.addAnnotation(annotation)
        }
        // The ONE selection's box on this page (picked here, in the Inspector or the Reader): its handles
        // in Edit Segments, an outline otherwise -- swept with the boxes.
        if let selected = owner.segmentEditing.selected {
            let marks = owner.segmentEditing.isEditing
                ? PDFShapeAnnotations.handles(for: selected.box, on: page, scale: view.scaleFactor, userName: Self.ocrBoxAnnotationName)
                : PDFShapeAnnotations.selectionOutline(for: selected.box, on: page, userName: Self.ocrBoxAnnotationName)
            marks.forEach(page.addAnnotation)
        }
    }

    static let ocrBoxAnnotationName = "fichero.ocr-box"

    /// The drawn boxes that come from segments, placed in page space by the squares' own rule
    /// (unrotated, flipped, offset by the crop), for the PDF view's accessibility elements (#5192).
    static func segmentBoxes(_ boxes: [OCRGeometryBox], on page: PDFPage, selectedId: String?) -> [PDFSegmentBox] {
        let crop = page.bounds(for: .cropBox)
        return boxes.compactMap { box in
            guard let segmentId = box.segmentId,
                  let rect = PDFRegionGeometry.pageRect(
                      normalized: PDFRegionGeometry.unrotated(normalized: box.bbox, rotation: page.rotation),
                      pageSize: crop.size
                  ) else { return nil }
            return PDFSegmentBox(
                segmentId: segmentId, kind: box.level, pageRect: rect.offsetBy(dx: crop.minX, dy: crop.minY),
                selected: segmentId == selectedId
            )
        }
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
    /// WHEN THE PAGE HAS NO GEOMETRY, NOTHING IS DRAWN — decided, not inherited.
    ///
    /// The loader asks the PAGE document, and if that page has no
    /// geometry-bearing artifact the overlay stays empty. It does NOT fall
    /// back to the parent PDF's own artifacts, and that is the point of the
    /// change rather than an omission in it: a whole-document artifact carries
    /// ONE page's boxes, and drawing them here would put them on whichever
    /// page happens to be open — the exact defect this replaced, reintroduced
    /// as a fallback.
    ///
    /// Empty is also the honest answer. A page with no geometry artifact has
    /// not been processed; an artifact carrying zero boxes is the importer
    /// saying "this page is a scan, geometry is unavailable" (#4418). Neither
    /// is "here are some boxes from elsewhere in the book".
    ///
    /// The parent's geometry is still reachable — a pane the host cannot track
    /// falls back to the rendered document — but only through
    /// `boxesForDisplayedPage`, which drops every box naming another page.
    func loadOCRGeometry() async {
        ocrGeometry = nil
        guard ocrBoxesEnabled else { return }

        // THE SEAM FIRST (#4954, `source.app.overlays-draw-from-the-seam`): the same
        // shared function the image overlay now reads, so the two paths cannot diverge.
        // `boxesForDisplayedPage` still drops every box naming another page, so a PDF
        // pane shows its own page's boxes exactly as before — the seam changes where the
        // boxes come from, never which page they belong to.
        if let segmentService {
            let store = SegmentStore.shared(for: segmentService)
            await store.load(documentId: effectiveGeometryDocumentId)
            if let selected = SegmentDisplay.selected(
                for: effectiveGeometryDocumentId, store: store
            ) {
                ocrGeometry = selected.geometry
                return
            }
        }

        guard let artifactService else { return }
        do {
            ocrGeometry = try await OCRGeometrySelection.load(
                documentId: effectiveGeometryDocumentId,
                using: artifactService
            )
        } catch {
            // Render nothing and say so in the log rather than silently — no
            // boxes must not be indistinguishable from a failed fetch (#4418).
            ocrBoxesLogger.error(
                "OCR geometry load failed for \(effectiveGeometryDocumentId): \(String(describing: error))"
            )
        }
    }
}
#endif
