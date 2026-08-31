#if os(macOS)
import SwiftUI

extension ZoomableImagePreview {
    /// Both box overlays, framed to the DRAWN image rect — never the pane.
    /// Pane-spanning overlays put boxes in the letterbox (2026-08-12 bbox
    /// repro). `geometry.visible` and `geometry.drawnFrame` describe the same
    /// crop and arrive in one write, so the mapping stays consistent while
    /// panning — it used to be two independent writes, and the pair could
    /// disagree mid-gesture (2026-08-20 bbox review, D3).
    @ViewBuilder
    var boxOverlays: some View {
        // Nothing renders until a layout pass has measured BOTH rects
        // (2026-08-20 bbox review, D5). The old unit-rect fallback left the
        // overlay unframed before the first measurement — spanning the whole
        // pane — and mapped boxes against the full image, flashing them across
        // the pane on every image load. An unmeasured viewport is not a
        // viewport showing the whole image; drawing nothing for one frame is
        // the honest answer, and the Every Frame Perfect one.
        if geometry.isMeasured {
            ZStack(alignment: .topLeading) {
                // Entry-source highlight FIRST — a soft wash BEHIND the word
                // boxes, visually distinct from annotation regions (Daniel,
                // 2026-08-21: "wrong color… it should be behind words").
                // Where it lands is the anchor DATA's problem (Step-4
                // re-anchor); how it reads is this layer's.
                ForEach(Array(highlightBoxes.enumerated()), id: \.offset) { _, box in
                    if let rect = BoundingBoxGeometry.viewRect(
                        normalized: box,
                        in: geometry.drawnFrame.size,
                        visible: geometry.visible
                    ) {
                        RoundedRectangle(cornerRadius: 3)
                            .fill(Color.yellow.opacity(0.22))
                            .frame(width: rect.width, height: rect.height)
                            .offset(x: rect.minX, y: rect.minY)
                            .allowsHitTesting(false)
                    }
                }
                // Words lit by the READER's text selection (2026-08-23
                // linking) — sharper than the entry wash so the specific
                // words read against it.
                ForEach(Array(linkedSelectionBoxes.enumerated()), id: \.offset) { _, box in
                    if let rect = BoundingBoxGeometry.viewRect(
                        normalized: box,
                        in: geometry.drawnFrame.size,
                        visible: geometry.visible
                    ) {
                        RoundedRectangle(cornerRadius: 2)
                            .fill(Color.accentColor.opacity(0.28))
                            .frame(width: rect.width, height: rect.height)
                            .offset(x: rect.minX, y: rect.minY)
                            .allowsHitTesting(false)
                    }
                }
                // Saved annotations, rendered BY KIND (Daniel, 2026-08-30:
                // a highlight is a wash, an underline a bar, a check a ✓ in
                // the margin — markup should LOOK like what it is).
                if annotationsEnabled && !annotationMarks.isEmpty {
                    AnnotationMarkLayer(marks: annotationMarks, visible: geometry.visible)
                }
                // The region-DRAW layer (#2458): drag plumbing only — the
                // saved marks above own display now, so it draws no boxes.
                if isDrawingRegion {
                    BoundingBoxOverlay(
                        boxes: [],
                        visible: geometry.visible,
                        isDrawing: true,
                        onCreate: { box in createAnnotation(box: box, tool: pendingAnnotationTool) }
                    )
                }
                // OCR text boxes from the transcription pass (#4309),
                // toggled from the reader toolbar. FRAME GATE (2026-08-23,
                // entry-scoped runs): a box set naming a rendition_id was
                // measured on THAT rendition's pixels — drawing it over any
                // other image places plausible boxes in the wrong frame, the
                // same defect class as the misplaced spread band. nil means
                // the document's own image; non-nil draws only when that
                // exact rendition is what's on screen.
                if ocrBoxesEnabled, let ocrGeometry,
                   geometryFrameMatchesDisplay(ocrGeometry) {
                    OCRGeometryOverlay(
                        geometry: ocrGeometry,
                        visible: geometry.visible
                    )
                }
                // Regions as first-class (2026-08-29): the INTERACTIVE layer
                // — click-to-select, ⇧-click, drag-to-move, rubber-band add,
                // marquee display. Above the inert canvas; builds views only
                // for the few SELECTED boxes, so the one-Canvas perf fix
                // stands.
                regionInteractionLayer
            }
            .frame(width: geometry.drawnFrame.width, height: geometry.drawnFrame.height)
            // Boxes never bleed past the drawn image into the letterbox or the
            // neighbouring panes (user, 2026-08-20: "they draw over the image
            // and sometimes into other views").
            .clipped()
            .offset(x: geometry.drawnFrame.minX, y: geometry.drawnFrame.minY)
        }
    }
}

extension ZoomableImagePreview {
    // Moved from the main file 2026-08-23 (file/type length): same member.
    // QUIET since 2026-08-29 (Daniel): paging/renditions live in the pane
    // head, markup in the head's slide-out row, and the magnification family
    // in the floating cluster beside the mini-map. This bar keeps only the
    // regions toggle — the ⓘ went too (2026-08-30: it only toggled the
    // inspector, which has its own affordances).
    var readerToolbar: some View {
        ReaderToolbar(
            style: .quiet,
            onShowInfo: {
                NotificationCenter.default.post(name: .previewShowInfo, object: nil)
            },
            scalePercent: Int(scale * 100),
            zoomIn: zoomIn,
            zoomOut: zoomOut,
            fitToWindow: fitToWindow,
            actualSize: actualSize,
            textBoxesEnabled: $ocrBoxesEnabled,
            annotationsEnabled: $annotationsEnabled
        )
    }
}

extension ZoomableImagePreview {
    /// The main canvas: tracking image + box overlays + the magnification
    /// family cluster (mini-map / zoom pill / loupe + magnifier toggles,
    /// bottom-right — Daniel, 2026-08-29) + the magnifier strip. Extracted
    /// from `body` (2026-08-29) for the type-length budget.
    var canvasArea: some View {
        // Main content area. The reader toolbar (zoom / magnifier / loupe /
        // edit / annotation) now lives at the BOTTOM of the canvas via the
        // shared ReaderToolbar (#2423), so the image and PDF readers present
        // one identical, persistent bar.
        ZStack(alignment: .bottomTrailing) {
            VStack(spacing: 0) {
                if renderedImage != nil || url != nil {
                    ImageWithCursorTracking(
                        url: url,
                        // A backend-rendered rendition WINS over the
                        // high-res source (2026-08-20 bbox review, D2).
                        // The old `highResImage ?? renderedImage` let the
                        // zoom-triggered source fetch replace the very
                        // rendition the user chose to look at — different
                        // pixels, and for a crop/rotate/deskew/split
                        // rendition a different FRAME, which moves every
                        // box on the page.
                        overrideImage: renditionOverrideImage ?? renderedImage ?? highResImage,
                        // Rendition index in the key: a flip counts as
                        // an ITEM change so the view refits — renditions
                        // have different pixel sizes, and preserving
                        // apparent width left one at 70% and the next at
                        // 26% (Daniel, 2026-08-22).
                        itemKey: "\(documentId ?? "")#r\(renditionIndex)",
                        focusRegion: focusRegion,
                        scale: $scale,
                        cursorPosition: $cursorPosition,
                        imageSize: $imageSize,
                        geometry: $geometry,
                        minScale: minScale,
                        maxScale: maxScale,
                        loupeEnabled: loupeIsOn,
                        loupeLocked: loupeLocked,
                        loupeMagnification: Binding(
                            get: { CGFloat(loupeMagnification) },
                            set: { loupeMagnification = Double($0) }
                        ),
                        loupeSize: Binding(
                            get: { CGFloat(loupeSize) },
                            set: { loupeSize = Double($0) }
                        ),
                        coordinator: $imageCoordinator
                    )
                    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .center)
                    .overlay(alignment: .topLeading) {
                        boxOverlays
                    }
                } else {
                    ProgressView()
                        .controlSize(.small)
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                }

                // Bottom magnifier panel
                if magnifierEnabled, let img = image {
                    Divider()
                    MagnifierPanelView(
                        image: img,
                        cursorPosition: magnifierPosition,
                        imageSize: imageSize,
                        magnification: Binding(
                            get: { CGFloat(panelMagnification) },
                            set: { panelMagnification = Double($0) }
                        ),
                        panelHeight: Binding(
                            get: { CGFloat(panelHeight) },
                            set: { panelHeight = Double($0) }
                        ),
                        isLocked: $magnifierLocked,
                        onLockToggle: {
                            if !magnifierLocked {
                                // Locking - save the current magnifier position
                                lockedPosition = cursorPosition
                            }
                            magnifierLocked.toggle()
                        }
                    )
                    .frame(height: CGFloat(panelHeight))
                }
            }
            .background(Color(nsColor: .windowBackgroundColor))

            // The magnification family, TOP-right (Daniel, 2026-08-30 —
            // moved up from the bottom corner): mini-map on top, zoom pill
            // under it, loupe + magnifier-bar toggles below. The map keeps
            // its #771 guard — it appears only when zoomed in (or the loupe
            // is up); without it the cluster collapses to the pill + toggles.
            let isActuallyZoomed = geometry.isMeasured
                && (geometry.visible.width < 0.99 || geometry.visible.height < 0.99)
            PreviewZoomMapCluster(
                scalePercent: Int(scale * 100),
                zoomIn: zoomIn,
                zoomOut: zoomOut,
                fitToWindow: fitToWindow,
                actualSize: actualSize,
                loupeEnabled: $loupeEnabled,
                magnifierEnabled: $magnifierEnabled,
                map: {
                if let img = image, isActuallyZoomed || loupeIsOn {
                    NavigatorMiniMap(
                        image: img,
                        visibleRect: geometry.visible,
                        onRectangleDragged: { normalizedOrigin in
                            imageCoordinator?.scrollToNormalizedPosition(normalizedOrigin)
                        }
                    )
                    .frame(width: 150, height: 100)
                }
            })
            // Pin to the TOP-right corner regardless of the ZStack's
            // bottom-anchored alignment (the magnifier strip still slides
            // from the bottom edge, so the cluster no longer needs to
            // dodge it).
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topTrailing)
        }
        .onHover { inside in
            hoveringCanvas = inside
            applyMarkupCursor()
        }
    }
}

extension ZoomableImagePreview {
    /// The armed tool's cursor, applied while the pointer is over the canvas
    /// (Daniel, 2026-08-30: "when we change tools for markup, the cursor
    /// changes"). `.set()` rather than push/pop — tool changes mid-hover
    /// would unbalance a stack.
    func applyMarkupCursor() {
        guard hoveringCanvas else { return }
        switch windowState?.activeMarkupTool {
        case .textSelect, .note: NSCursor.iBeam.set()
        case .check: NSCursor.pointingHand.set()
        case .drawRegion, .select, .line, .highlight, .wordSelect: NSCursor.crosshair.set()
        default: NSCursor.arrow.set()
        }
    }
}

#endif
