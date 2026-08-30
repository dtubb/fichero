import Foundation
import Observation

/// Shared selection holder for REGION NODES — documents carrying
/// `regionInParent` — selected in the document inspector's regions list
/// (Daniel, 2026-08-29: the workflow bar's run scope must follow the
/// selection the user can SEE, and N regions picked in the inspector ARE
/// that selection).
///
/// The same id-plus-context shape as `FocusedArtifact.shared`: the inspector
/// pane that owns region rows writes here; the workflow bar (and any other
/// launch surface) reads it to resolve its run scope. A process-wide shared
/// instance, not environment plumbing, because the writer (inspector) and
/// the reader (ContentView's bar hosting) live in different view subtrees —
/// exactly why `FocusedArtifact` is shaped this way.
///
/// SHARED SEAM: written by the inspector's region-selection UI (owned by the
/// preview-regions lane), read by the workflow bar's scope resolution. Keep
/// this file free of UI so both lanes can meet here without merge conflicts.
@Observable
@MainActor
final class FocusedRegionSelection {
    /// Process-wide shared selection, mirroring `FocusedArtifact.shared`.
    static let shared = FocusedRegionSelection()

    /// The selected region NODE ids, in the order the list presents them.
    /// Region nodes are real documents (with `regionInParent`), so these ids
    /// are valid `selected_doc_ids` for a workflow run.
    private(set) var regionDocumentIds: [String] = []

    /// The page the regions belong to. The bar honors this selection only
    /// while that page is the one being inspected — a lingering selection
    /// from a page the user has left is not "the selection you can see".
    private(set) var parentDocumentId: String?

    /// Human label for the parent page, so the target chip can say
    /// "5 regions of 4_Hoja_531_Verso" without a store lookup.
    private(set) var parentDocumentName: String?

    init() {}

    /// Replace the selection. Called by the inspector's region list whenever
    /// its selection changes; an empty `ids` is equivalent to `clear()`.
    func select(_ ids: [String], parentDocumentId: String?, parentDocumentName: String?) {
        regionDocumentIds = ids
        self.parentDocumentId = ids.isEmpty ? nil : parentDocumentId
        self.parentDocumentName = ids.isEmpty ? nil : parentDocumentName
    }

    /// Clear the selection (document switch, pane closed, rows deselected).
    func clear() {
        regionDocumentIds = []
        parentDocumentId = nil
        parentDocumentName = nil
    }
}
