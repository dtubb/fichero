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
    /// Same ladder the overlay always had — words when the pass produced
    /// them, lines otherwise — extended one honest rung: a geometry carrying
    /// ONLY region-level boxes (hand-drawn or combined regions) used to
    /// render nothing at all, which made curated regions invisible the
    /// moment they were curated.
    var displayIndexedBoxes: [(index: Int, box: OCRGeometryBox)] {
        let indexed = boxes.enumerated().map { (index: $0.offset, box: $0.element) }
        let words = indexed.filter { $0.box.level == "word" }
        if !words.isEmpty { return words }
        let lines = indexed.filter { $0.box.level == "line" }
        if !lines.isEmpty { return lines }
        return indexed
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
