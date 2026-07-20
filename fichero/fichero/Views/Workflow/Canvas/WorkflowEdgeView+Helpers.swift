import SwiftUI

// MARK: - Fan role classification
//
// The backend's LangGraph builder runs implicit fan-out/fan-in around
// per-file tools: Transcribe runs N times in parallel, Catalogue collects
// the N results before running once. That structure is invisible in a
// linear `Files → Transcribe → Catalogue` canvas, which is exactly the
// confusion the user reported. These role annotations let us render a
// badge on the edge so the user can SEE when files fan out and when
// they merge back.
//
// Static tool-name → role for 0.0.2. A future revision pushes this
// metadata from the backend ToolDef so adding a tool doesn't need a
// frontend edit.

enum EdgeFanRole: Equatable {
    case fanOut
    case fanIn
    case none

    func label(count: Int?) -> String {
        switch self {
        case .fanOut: return count.map { "→ \($0) files" } ?? "fan-out"
        case .fanIn:  return count.map { "∑ \($0) files" } ?? "merge"
        case .none:   return ""
        }
    }
}

/// Tools whose invocation fans out across files (one call per file).
private let fanOutTools: Set<String> = [
    "transcribe", "describe", "classify", "caption", "analyze", "tags",
    "colors", "faces", "layout", "compare", "convert", "extract", "objects",
    "scene", "quality", "safety", "diagram", "table_extract", "handwriting",
    "style", "similarity",
    "audio_transcribe", "video_describe"
]

/// Tools that collapse fan-out results into a single payload.
private let fanInTools: Set<String> = [
    "aggregate",
    "catalogue",
    "write_file",
    "people_extract", "dates_extract", "rivers_extract", "events_extract",
    "mines_extract", "properties_extract", "legal_references_extract",
    "keywords_extract"
]

enum EdgeFanRoleResolver {
    static func role(sourceTool: String?, targetTool: String?) -> EdgeFanRole {
        if let target = targetTool, fanInTools.contains(target) {
            return .fanIn
        }
        if let source = sourceTool, fanOutTools.contains(source) {
            return .fanOut
        }
        return .none
    }
}
