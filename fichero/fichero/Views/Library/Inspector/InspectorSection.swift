import SwiftUI

/// The four top-level inspector tabs (down from ten) — the approved
/// information architecture (#3434, design doc 2026-07-11). Daniel picked the
/// **top icon row** switcher, so these render as four labelled icons across the
/// top of the inspector (the existing `DocumentInspector.tabBar` pattern).
///
/// This is the canonical grouping *contract*: it maps every legacy
/// ``InspectorTab`` facet into exactly one section (see ``facets``), so the
/// DocumentInspector rewire — and `WorkflowInspector`, which reuses the same
/// chrome — share one source of truth for the 10→4 fold instead of duplicating
/// it. Image **Edits** is deliberately absent: it leaves the inspector for the
/// Reader canvas toolbar.
enum InspectorSection: String, CaseIterable, Identifiable {
    case source = "Source"
    case artifacts = "Artifacts"
    case knowledge = "Knowledge"
    case notes = "Notes"

    var id: String { rawValue }

    /// The legacy facets this section absorbs, in display order. The inspector
    /// reuses each facet's existing body (iterate, don't replace); single-facet
    /// sections render it directly, multi-facet sections switch among them.
    var facets: [InspectorTab] {
        switch self {
        case .source:    return [.content, .info]
        case .artifacts: return [.artifacts]
        case .knowledge: return [.entities, .knowledgeGraph, .citations]
        case .notes:     return [.notes, .annotations, .interpretations]
        }
    }

    var icon: String {
        switch self {
        case .source:    return "doc.text"
        case .artifacts: return "shippingbox"
        case .knowledge: return "point.3.connected.trianglepath.dotted"
        case .notes:     return "pencil.and.scribble"
        }
    }

    /// Tooltip copy: what the tab is and how to use it.
    var helpText: String {
        switch self {
        case .source:
            return "Source — what the document is: its text, outline, metadata, and storage location"
        case .artifacts:
            return "Artifacts — workflow outputs like transcriptions, catalogues, translations, and summaries, with lineage"
        case .knowledge:
            return "Knowledge — entities, claims, predictions, and citations for this selection; the database editor"
        case .notes:
            return "Notes — your annotations, free notes, and interpretation: the human reading layer"
        }
    }

    /// Stable per-tab XCUITest hook, e.g. "inspectorSection-Source".
    var accessibilityIdentifier: String { "inspectorSection-\(rawValue)" }

    /// Which section a legacy facet belongs to. `.edits` returns `nil` — it is
    /// no longer an inspector tab (it moves to the Reader canvas).
    static func section(for tab: InspectorTab) -> InspectorSection? {
        allCases.first { $0.facets.contains(tab) }
    }
}

/// Adopt the shared top-tab chrome (#3530): the inspector section bar is now a
/// `SurfaceTabBar<InspectorSection>`, the same icon row the Reader uses.
extension InspectorSection: SurfaceTab {
    var title: String { rawValue }
    var help: String { helpText }
    var accessibilityID: String { accessibilityIdentifier }
}
