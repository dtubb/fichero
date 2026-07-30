import SwiftUI

/// Draws the transcription's word/line boxes over the page image (#4309).
///
/// A sibling of `BoundingBoxOverlay` (user annotation regions): this layer
/// renders the OCR geometry captured on the vision pass — normalized
/// top-left-origin `[x, y, w, h]` rects — inside the currently visible
/// zoom/pan window. Hovering a box highlights it and shows its recognized
/// text, previewing the transcript↔image link the geometry stores.
struct OCRGeometryOverlay: View {
    let geometry: OCRGeometry
    /// Normalized sub-rect of the image currently visible (zoom/pan window).
    let visible: CGRect

    @State private var hoveredBoxID: String?

    /// Words when the pass produced them; lines otherwise (never both at
    /// once — nested rectangles read as clutter, not structure).
    private var boxes: [OCRGeometryBox] {
        let words = geometry.wordBoxes
        return words.isEmpty ? geometry.lineBoxes : words
    }

    var body: some View {
        GeometryReader { geo in
            ZStack(alignment: .topLeading) {
                ForEach(boxes) { box in
                    if let rect = BoundingBoxGeometry.viewRect(
                        normalized: box.bbox, in: geo.size, visible: visible
                    ) {
                        let isHovered = hoveredBoxID == box.id
                        RoundedRectangle(cornerRadius: 1.5)
                            .stroke(
                                isHovered ? Color.orange : Color.accentColor.opacity(0.8),
                                lineWidth: isHovered ? 1.5 : 1
                            )
                            .background(
                                (isHovered ? Color.orange : Color.accentColor)
                                    .opacity(isHovered ? 0.22 : 0.08)
                            )
                            .frame(width: rect.width, height: rect.height)
                            .offset(x: rect.minX, y: rect.minY)
                            .onHover { inside in
                                hoveredBoxID = inside ? box.id : (isHovered ? nil : hoveredBoxID)
                            }
                            .help(box.text)
                            .accessibilityLabel("Recognized text: \(box.text)")
                    }
                }
            }
            .frame(width: geo.size.width, height: geo.size.height)
        }
        .allowsHitTesting(true)
    }
}

#if os(macOS)
extension ZoomableImagePreview {
    /// Fetch the latest transcription artifact's typed geometry for this page.
    /// List first (lean payload), then the single GET which carries geometry
    /// (#4309). Lives here so the (large) preview struct body stays under the
    /// type-body-length budget.
    func loadOCRGeometry() async {
        ocrGeometry = nil
        guard ocrBoxesEnabled, let documentId, let artifactService else { return }
        do {
            let transcriptions = try await artifactService.getArtifacts(
                forDocumentId: documentId,
                type: "transcription",
                includeDescendants: false
            )
            guard let latest = transcriptions.max(by: { $0.createdAt < $1.createdAt }) else {
                return
            }
            let full = try await artifactService.getArtifact(id: latest.id)
            ocrGeometry = full.ocrGeometry
        } catch {
            // Surface in the log, render nothing — the toggle stays honest
            // (no boxes ≠ silent success).
            Self.logger.error(
                "OCR geometry load failed for \(documentId): \(String(describing: error))"
            )
        }
    }
}
#endif
