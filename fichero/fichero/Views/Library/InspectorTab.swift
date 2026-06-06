import SwiftUI

// MARK: - Notification Names

extension Notification.Name {
    /// Posted when a claim is selected in the inspector
    static let claimSelectedInInspector = Notification.Name("claimSelectedInInspector")
}

/// Tab selection for document inspector. Order matters — left-to-right is
/// content / entities / knowledge graph / artifacts / info, per Daniel's
/// mental model: "the document itself" → "extracted entities" → "structured
/// claims" → "the raw outputs" → "metadata about the document".
enum InspectorTab: String, CaseIterable, Identifiable {
    case content = "Content"
    case outline = "Outline"
    case annotations = "Annotations"
    case notes = "Notes"
    case entities = "Entities"
    case knowledgeGraph = "Knowledge Graph"
    case artifacts = "Artifacts"
    case edits = "Edits"
    case info = "Info"

    var id: String { rawValue }

    var icon: String {
        switch self {
        case .content: return "doc.text"
        case .outline: return "list.bullet.indent"
        case .annotations: return "highlighter"
        case .notes: return "pencil.and.scribble"
        case .entities: return "person.text.rectangle"
        case .knowledgeGraph: return "point.3.connected.trianglepath.dotted"
        case .artifacts: return "shippingbox"
        case .edits: return "slider.horizontal.3"
        case .info: return "info.circle"
        }
    }

    /// Tooltip copy: what the tab is and how to use it. (#1371)
    var helpText: String {
        switch self {
        case .content:
            return "Content — read the document's extracted text and page contents"
        case .outline:
            return "Outline — drill down the document's structure: chapters, sections, pages, and what's on each"
        case .annotations:
            return "Annotations — view and edit highlights and notes on this document"
        case .notes:
            return "Notes — free-text research notes linked to this document"
        case .entities:
            return "Entities — extracted people, places, organizations, and concepts"
        case .knowledgeGraph:
            return "Knowledge graph — structured SVO claims and interpretations for this document"
        case .artifacts:
            return "Artifacts — outputs generated for this document, such as summaries and transcripts"
        case .edits:
            return "Edits — non-destructive image/page edit operations for this document"
        case .info:
            return "Info — file metadata: type, size, dates, and storage location"
        }
    }
}
