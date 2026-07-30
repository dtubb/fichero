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
    }
}

/// Typed OCR/transcription geometry for one artifact (#4309): the text plus
/// its word/line boxes, as produced by the vision pass that transcribed it.
struct OCRGeometry: Codable, Hashable {
    var text: String
    var provider: String
    var model: String?
    var boxes: [OCRGeometryBox]

    var lineBoxes: [OCRGeometryBox] { boxes.filter { $0.level == "line" } }
    var wordBoxes: [OCRGeometryBox] { boxes.filter { $0.level == "word" } }
}

// MARK: - Generated-client mapping

extension OCRGeometry {
    /// Map the generated OpenAPI payload into the app model. Boxes without a
    /// level default to "word", matching the backend contract's default.
    init(generated: Components.Schemas.OCRGeometryResult) {
        self.text = generated.text ?? ""
        self.provider = generated.provider
        self.model = generated.model
        self.boxes = (generated.boxes ?? []).map { box in
            OCRGeometryBox(
                text: box.text,
                bbox: box.bbox,
                level: box.level?.rawValue ?? "word",
                confidence: box.confidence,
                pageIndex: box.pageIndex,
                charStart: box.charStart,
                charEnd: box.charEnd
            )
        }
    }
}
