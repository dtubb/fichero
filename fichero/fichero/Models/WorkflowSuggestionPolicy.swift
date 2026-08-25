import Foundation

/// Which workflows the toolbar offers for the CURRENT selection — the pure
/// policy behind the island's contextual buttons (Daniel, 2026-08-25:
/// "toolbar buttons that appear as things are selected… select a folder and
/// you can catalogue").
///
/// Phase 1 works from facts the selection already carries (docType/fileType/
/// nodeKind) — no fetches, no model calls. The artifact-aware tier ("has a
/// transcription → offer entities") arrives when the outline endpoint's
/// attachment summary gains its client consumer; this type is where that
/// refinement lands without the toolbar changing.
struct WorkflowSuggestion: Equatable, Identifiable {
    /// Canonical DEFAULT-workflow name — resolved to this library's workflow
    /// id at render time (ids are per-library; names are the stable key).
    let workflowName: String
    let systemImage: String
    var id: String { workflowName }
}

enum WorkflowSuggestionPolicy {

    /// At most two suggestions — the strip is a nudge, not a menu. The ⚡
    /// picker beside it always offers everything.
    static func suggestions(for documents: [Document]) -> [WorkflowSuggestion] {
        guard !documents.isEmpty else { return [] }

        // A folder selection is the catalogue-and-fan-out case.
        if documents.allSatisfy({ $0.docType == .folder }) {
            return [
                WorkflowSuggestion(workflowName: "Catalogue", systemImage: "list.bullet.rectangle"),
                WorkflowSuggestion(workflowName: "Transcribe (Auto-Detect)", systemImage: "text.viewfinder"),
            ]
        }

        // Extracted entries: the reading is done — structure it.
        if documents.allSatisfy({ $0.nodeKind == "entry" }) {
            return [
                WorkflowSuggestion(workflowName: "Extract Entities", systemImage: "person.text.rectangle"),
                WorkflowSuggestion(workflowName: "Extract SVO → Claims", systemImage: "point.3.connected.trianglepath.dotted"),
            ]
        }

        // Images and pages: reading comes first.
        if documents.allSatisfy({ $0.fileType == .image || $0.docType == .page }) {
            return [
                WorkflowSuggestion(workflowName: "Transcribe (Auto-Detect)", systemImage: "text.viewfinder"),
                WorkflowSuggestion(workflowName: "Detect Regions", systemImage: "rectangle.dashed"),
            ]
        }

        // Mixed or unknown: no nudge — the ⚡ picker carries it.
        return []
    }
}
