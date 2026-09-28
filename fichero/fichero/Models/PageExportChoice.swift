import Foundation

/// A page's export choices (#5162; `source.format.export-choices`): which pass, in which format --
/// built from what the engine WRITES (`GET /api/formats`), not a list kept in the app -- and "as
/// imported", the pass's original file byte for byte. Offered per pass in Inspector › Making. Pure.
enum PageExportChoice {
    struct Format: Equatable, Identifiable {
        let name: String
        /// As the engine declares them, first the usual one (".hocr", ".txt").
        let extensions: [String]
        let writes: Bool
        var id: String { name }
        var title: String { PageExportChoice.title(name) }
    }

    /// What the engine says it exported (its `choices`), as the export's summary reads it.
    struct Stated {
        let passName: String?
        let passBasis: String?
        let orderName: String?
        let readingKind: String?
        let segmentCount: Int
    }

    /// Formats that write a georeference (control points and a mask), offered only for a
    /// georeferencing pass; the others write text and shapes, offered only for a text pass.
    static let georeferenceFormats: Set<String> = ["iiif-georef", "qgis-points"]

    /// The order a person meets them: the four scholarly text formats first (PAGE XML is what
    /// eScriptorium and Transkribus read), then the rest; a format this list does not know comes last.
    private static let order = ["pagexml", "alto", "tei", "hocr", "yolo", "iiif-georef", "qgis-points"]

    static func title(_ name: String) -> String {
        switch name {
        case "pagexml": "PAGE XML"
        case "alto": "ALTO"
        case "tei": "TEI"
        case "hocr": "hOCR"
        case "yolo": "YOLO"
        case "iiif-georef": "IIIF Georeference"
        case "qgis-points": "QGIS Points"
        default: name.uppercased()
        }
    }

    /// What a pass can be written as: what the engine writes, of the pass's own kind.
    static func offers(_ formats: [Format], georeferencing: Bool) -> [Format] {
        formats
            .filter { $0.writes && georeferenceFormats.contains($0.name) == georeferencing }
            .sorted { (order.firstIndex(of: $0.name) ?? order.count, $0.name) < (order.firstIndex(of: $1.name) ?? order.count, $1.name) }
    }
}
