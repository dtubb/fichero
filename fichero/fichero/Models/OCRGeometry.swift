import FicheroAPIClient
import Foundation

// MARK: - OCR Geometry (#4309)

/// One recognized text box over a page image — normalized `[x, y, w, h]` in
/// 0…1, top-left origin. Mirrors the backend `OCRGeometryBox` contract.
///
/// `charStart`/`charEnd` are the box's character span inside the owning
/// artifact's content string: the box↔text link that lets a later content edit
/// re-map its segment rather than orphaning the geometry.
struct OCRGeometryBox: Codable, Hashable, Identifiable {
    var text: String
    /// Normalized `[x, y, width, height]`, 0…1, top-left origin.
    var bbox: [Double]
    /// "line", "word", "block", "page", or "region".
    var level: String
    /// How sure the producer is about WHERE this box is — not about what it
    /// says. Absent when the producer does not report one (the alignment pass
    /// writes none), which is silence, not doubt: `OCRBoxConfidence` is the
    /// one place that distinction is decided.
    var confidence: Double?
    var pageIndex: Int?
    var charStart: Int?
    var charEnd: Int?
    /// Who put this box here, and how. The engine has stamped
    /// `provider: "user"` / `source: "manual"` on every hand-drawn region
    /// since the region verbs landed; this mirror dropped both, so the app
    /// could not tell a box a PERSON drew from one a model estimated
    /// (2026-09-03). Curation you cannot see is curation you will overwrite.
    var provider: String?
    var source: String?

    /// What the segment draws as, beyond its box: polygon, path, point, baseline (`SegmentShapes`).
    /// Empty for a box and for artifact geometry; not part of the artifact wire format.
    var shapes: [SegmentShapes.Drawn] = []
    /// A segment left without a reading (`SegmentsPane.lacksReading`): drawn dashed and hollow, never hidden.
    var noReading = false
    /// The segment this box draws, when it comes from a segment pass (`SegmentDisplay.geometry`): the id a
    /// drawn box is known by from outside the app (`SegmentBox-<id>`, #5192). Not part of the artifact wire format.
    var segmentId: String?
    /// The segment this one sits in (`Segment.parentSegmentId`): how a child is drawn as its parent's child and a
    /// selection lights its children (`SegmentHierarchy`, #5426). Nil for a flat pass and for artifact geometry.
    /// Not part of the artifact wire format.
    var parentSegmentId: String?
    /// Its region's hue and its shade along the reading order (`RegionColours.tones`), from a segment pass;
    /// nil for artifact geometry, which is drawn in the plain box colour. Not part of the artifact wire format.
    var tone: RegionColours.Tone?

    /// A box a person drew, rather than a pass measuring one.
    var isHandDrawn: Bool { provider?.lowercased() == "user" || source?.lowercased() == "manual" }

    /// Stable identity for ForEach — geometry rows have no server id.
    var id: String { "\(level)-\(charStart ?? -1)-\(bbox.map { String($0) }.joined(separator: ","))" }

    enum CodingKeys: String, CodingKey {
        case text
        case bbox
        case level
        case confidence
        case pageIndex = "page_index"
        case charStart = "char_start"
        case charEnd = "char_end"
        case provider
        case source
    }
}

/// Typed OCR/transcription geometry for one artifact (#4309): the text plus
/// its word/line boxes, as produced by the vision pass that transcribed it.
struct OCRGeometry: Codable, Hashable {
    var text: String
    var provider: String
    var model: String?
    var boxes: [OCRGeometryBox]
    /// Which PICTURE the whole box set was measured on (2026-08-23,
    /// entry-scoped runs). `nil` means the document's own image — every
    /// artifact written before today. Non-nil means every box is a fraction
    /// of THAT rendition's frame (e.g. an entry's region crop) and must be
    /// resolved through the node's `regionInParent` before drawing on the
    /// parent image. On the SET, not per box: one result is measured on one
    /// picture, and per-box would let boxes disagree about something that
    /// cannot honestly differ. Treating this as ignorable provenance and
    /// drawing anyway is the failure mode — plausible boxes, wrong frame.
    var renditionId: String?

    var lineBoxes: [OCRGeometryBox] { boxes.filter { $0.level == "line" } }
    var wordBoxes: [OCRGeometryBox] { boxes.filter { $0.level == "word" } }

    /// The boxes the preview surfaces draw, WITH their positions in the full
    /// `boxes` list (2026-08-29, regions as first-class). The index is how
    /// the engine addresses a region for curation (move/delete/combine), so
    /// the display set must carry it — filtering first and enumerating after
    /// would renumber every box.
    ///
    /// EVERY level at once: regions, lines, words and letters (ruled 2026-10-05, hierarchy A, #5426,
    /// `source.editor.hierarchy.children-drawn-as-children`). A finer level never hides its parents: a page
    /// with words still draws its lines and regions under them, each lighter than its parent
    /// (`SegmentHierarchy`). The old ladder -- words only when the page had words -- made a page's lines and
    /// regions vanish the moment it had words; its older middle rung hid regions under lines (#5284).
    var displayIndexedBoxes: [(index: Int, box: OCRGeometryBox)] {
        boxes.enumerated().map { (index: $0.offset, box: $0.element) }
    }

    enum CodingKeys: String, CodingKey {
        case text, provider, model, boxes
        case renditionId = "rendition_id"
    }
}

// MARK: - Generated-client mapping

extension OCRGeometry {
    /// Map the generated OpenAPI payload into the app model. Boxes without a
    /// level default to "word", matching the backend contract's default.
    ///
    /// Per-box PROVENANCE rides along (2026-09-03). The engine stamps
    /// `provider: "user"` / `source: "manual"` on every hand-drawn region and
    /// has since the region verbs landed; this mapping dropped both, so no
    /// surface in the app could tell a box a PERSON drew from one a model
    /// estimated — the same shape as `wireAnchor` dropping `rendition_id`.
    /// A hand mapping that silently loses a field the generated schema
    /// carries is the recurring defect on this path.
    init(generated: Components.Schemas.OCRGeometryResult) {
        self.text = generated.text ?? ""
        self.provider = generated.provider
        self.model = generated.model
        self.renditionId = generated.renditionId
        self.boxes = (generated.boxes ?? []).map { box in
            OCRGeometryBox(
                text: box.text,
                bbox: box.bbox,
                level: box.level?.rawValue ?? "word",
                confidence: box.confidence,
                pageIndex: box.pageIndex,
                charStart: box.charStart,
                charEnd: box.charEnd,
                provider: box.provider,
                source: box.source
            )
        }
    }
}
