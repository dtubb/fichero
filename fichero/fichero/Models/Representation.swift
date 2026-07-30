import Foundation

/// One switchable view of a document/page (#2264, reform master plan §H).
///
/// A page has N representations derived from its artifacts: the original image,
/// and any conversions a workflow has produced — Markdown, HTML, SVG, a
/// spreadsheet table, a 2D world-map, or a 3D globe. `Representation.from(artifactType:)`
/// maps a stored artifact to the kind it renders as.
///
/// `image` is always present (the scanned page). The rest appear only when a
/// matching artifact exists. Only `image` and `markdown` are *rendered* today
/// (see ``DocumentCanvas``); the others are modelled here so a future reader
/// stage-picker and the backend presets (#2265) line up. The picker/store UI
/// that once lived alongside this enum was unwired scaffolding and was removed
/// (#3026); a real representation switcher belongs in UI Reform — Representations
/// (#2667). HTML/SVG need a raw-HTML web view, table needs `Table` over the rows,
/// and world-map / globe need the geo endpoint (#2266) plus the §7.8
/// SceneKit-vs-RealityKit call.
enum Representation: String, CaseIterable, Identifiable, Hashable {
    case image
    case markdown
    case html
    case svg
    case table
    case worldMap
    case globe

    var id: String { rawValue }

    var title: String {
        switch self {
        case .image: return "Image"
        case .markdown: return "Markdown"
        case .html: return "HTML"
        case .svg: return "SVG"
        case .table: return "Table"
        case .worldMap: return "Map"
        case .globe: return "Globe"
        }
    }

    var systemImage: String {
        switch self {
        case .image: return "photo"
        case .markdown: return "text.alignleft"
        case .html: return "chevron.left.forwardslash.chevron.right"
        case .svg: return "scribble.variable"
        case .table: return "tablecells"
        case .worldMap: return "map"
        case .globe: return "globe"
        }
    }

    /// True when ``DocumentCanvas`` can currently display this representation.
    /// The others are modelled but not yet wired (see the type doc).
    /// HTML/SVG render via `WebContentCanvas` (WebKit, scripts disabled) since
    /// #4329 — a conversion rendition is an alternate view of the same page.
    var isRenderable: Bool {
        switch self {
        case .image, .markdown, .html, .svg: return true
        default: return false
        }
    }

    /// The representation a given artifact type unlocks, or `nil` if none.
    ///
    /// Mirrors the backend tool artifact types: `convert` → conversion text
    /// (Markdown by default), `table_extract` → table, `extract_geo` → geo.
    static func from(artifactType: String) -> Representation? {
        switch artifactType {
        case "conversion", "transcription": return .markdown
        case "table": return .table
        case "geo": return .worldMap
        default: return nil
        }
    }
}
