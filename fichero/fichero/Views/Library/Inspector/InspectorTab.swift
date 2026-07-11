import SwiftUI

/// Tab selection for document inspector. Order matters — left-to-right is
/// content / artifacts / annotations / notes / entities / knowledge graph /
/// citations / edits / info, per Daniel's mental model: "the document itself"
/// → "workflow outputs" → "what was marked" → "what was noted" →
/// "extracted entities" → "structured claims" → "references" →
/// "edit tools" → "metadata about the document".
enum InspectorTab: String, CaseIterable, Identifiable {
    case content = "Content"
    case artifacts = "Artifacts"
    case annotations = "Annotations"
    case notes = "Notes"
    case interpretations = "Interpretation"
    case entities = "Entities"
    case knowledgeGraph = "Knowledge Graph"
    case citations = "Citations"
    case edits = "Edits"
    case info = "Info"

    var id: String { rawValue }

    var icon: String {
        switch self {
        case .content: return "doc.text"
        case .artifacts: return "shippingbox"
        case .annotations: return "highlighter"
        case .notes: return "pencil.and.scribble"
        case .interpretations: return "quote.bubble"
        case .entities: return "person.text.rectangle"
        case .knowledgeGraph: return "point.3.connected.trianglepath.dotted"
        case .citations: return "text.quote"
        case .edits: return "slider.horizontal.3"
        case .info: return "info.circle"
        }
    }

    /// Tooltip copy: what the tab is and how to use it. (#1371)
    var helpText: String {
        switch self {
        case .content:
            return "Content — read the document's extracted text and page contents"
        case .artifacts:
            return "Artifacts — inspect workflow outputs like transcriptions, catalogues, and summaries"
        case .annotations:
            return "Annotations — view and edit highlights and notes on this document"
        case .notes:
            return "Notes — free-text research notes linked to this document"
        case .interpretations:
            return "Interpretation — your own reading of this document, kept separate from the AI's facts and the source's quotations"
        case .entities:
            return "Entities — extracted people, places, organizations, and concepts"
        case .knowledgeGraph:
            return "Knowledge graph — structured SVO claims and provenance for this document"
        case .citations:
            return "Citations — documents this one cites and documents that cite it; includes the document's extracted bibliography"
        case .edits:
            return "Edits — non-destructive image/page edit operations for this document"
        case .info:
            return "Info — file metadata: type, size, dates, and storage location"
        }
    }
}
