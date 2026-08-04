import Foundation

// MARK: - Sidebar selection feeds the window's run selection (#4523)

extension ContentView {

    /// #4523: what a sidebar click on a document row contributes to the
    /// window's run selection. A FILE is an explicit pick of one document —
    /// the run scope. A FOLDER is a browse context, not a selection: it must
    /// NOT become the scope silently (that is the widening the confirmation
    /// dialog exists for), so it contributes nothing and the clear
    /// `handleSidebarItemChange` already performed stands. Pure and
    /// `nonisolated` so the rule is testable off-main (View statics inherit
    /// MainActor, #4201).
    nonisolated static func windowSelectionAfterSidebarApply(_ doc: Document) -> [String]? {
        doc.docType == .folder ? nil : [doc.id]
    }

    /// Apply a sidebar-resolved document: preview it AND record it as the
    /// window's selection.
    ///
    /// #4523 live regression (2026-08-04): a FILE picked in the sidebar IS
    /// the window's document selection — it is what the gallery is showing.
    /// Nothing wrote it into `preservedDocumentSelection` (only
    /// `handleBrowserSelectionChange` did, and a sidebar click CLEARS
    /// `browserSelection` on the way in), so navigating to a workflow and
    /// pressing Run resolved an empty selection and widened to the whole
    /// folder — six documents transcribed for one selected file. One
    /// selected document must run alone from every launch surface.
    func applySidebarSelectedDocument(_ doc: Document) {
        // Defer mutations to next run loop turn to avoid triggering multiple
        // FocusedValue updates in the same render cycle (#961).
        DispatchQueue.main.async {
            detailDocument = doc
            if let selected = Self.windowSelectionAfterSidebarApply(doc) {
                windowState.preservedDocumentSelection = selected
            }
        }
    }
}
