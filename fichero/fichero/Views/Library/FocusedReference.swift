import FicheroAPIClient
import Foundation
import Observation

/// One row in the references (bibliography) List — a `Reference` plus whether
/// it is the document's own self-reference (#2005, EPIC #2002).
///
/// The `ReferenceStore` exposes the bibliography as `selfRef` (the document's
/// own reference) plus `references` (the works it cites). We flatten them into
/// one `Identifiable` list — self-reference first — so the same
/// `List(selection:)` + detail pattern from `ArtifactListView` applies.
struct ReferenceItem: Identifiable, Hashable {
    let reference: Components.Schemas.Reference
    /// True for the document's own reference (rendered with a doc icon first).
    let isSelf: Bool

    /// Stable identity. `Reference.id` is optional, so fall back to the title.
    var id: String {
        if let refId = reference.id, !refId.isEmpty { return refId }
        return "ref|\(isSelf)|\(reference.title ?? reference.bibtex ?? "untitled")"
    }

    /// Best display title for the reference.
    var title: String {
        if let title = reference.title, !title.isEmpty { return title }
        if let bib = reference.bibtex, !bib.isEmpty { return String(bib.prefix(60)) + "…" }
        return "Untitled"
    }

    static func == (lhs: ReferenceItem, rhs: ReferenceItem) -> Bool { lhs.id == rhs.id }
    func hash(into hasher: inout Hasher) { hasher.combine(id) }
}

/// Shared selection holder for the references List + detail (#2005, EPIC #2002).
///
/// A per-domain copy of `FocusedArtifact`: the list writes the selected
/// reference id; the inline detail *and* the torn-off `ReferenceDetailWindow`
/// observe it. `ReferenceItem.shared` mirrors `FocusedArtifact.shared` so the
/// detached scene can follow the inspector's selection by reading one value.
@Observable
@MainActor
final class FocusedReference {
    /// Process-wide shared selection.
    static let shared = FocusedReference()

    /// The selected reference id (the `ReferenceItem.id`). Bound to
    /// `List(selection:)`; `nil` when nothing is selected.
    var id: String?

    /// The resolved item for `id`, kept in sync by the owning list pane — a
    /// value snapshot so the window can render without the store.
    private(set) var item: ReferenceItem?

    /// Human label for the document the selection belongs to — the detached
    /// window's subtitle.
    var documentName: String?

    init() {}

    /// Set the selection and resolve its snapshot against `items`.
    func select(_ id: String?, in items: [ReferenceItem]) {
        self.id = id
        resolve(in: items)
    }

    /// Re-resolve the snapshot for the current `id` against fresh `items`.
    func resolve(in items: [ReferenceItem]) {
        item = id.flatMap { selectedId in items.first { $0.id == selectedId } }
    }

    /// Clear the selection (e.g. on document switch).
    func clear() {
        id = nil
        item = nil
    }
}
