import CoreTransferable
import FicheroAPIClient
import Foundation
import Observation

/// One row in the citations List — a `DocumentCitation` plus the direction it
/// points relative to the inspected document (#2004, EPIC #2002).
///
/// The `CitationStore` exposes citations as *two* collections — `outbound`
/// (documents this one cites) and `inbound` (documents that cite this one) —
/// where `Artifact` was a single collection. We flatten them into one
/// `Identifiable` list so the same `List(selection:)` + detail pattern from
/// `ArtifactListView` applies unchanged; the `direction` is carried so a row
/// can show which side it's on and the detail can label it.
struct CitationItem: Identifiable, Hashable {
    enum Direction: String, Hashable {
        /// This document cites the target.
        case outbound
        /// Another document cites this one.
        case inbound

        var label: String { self == .outbound ? "Cites" : "Cited by" }
        var icon: String { self == .outbound ? "arrow.up.right" : "arrow.down.left" }
    }

    let citation: Components.Schemas.DocumentCitation
    let direction: Direction

    /// Stable identity. `DocumentCitation.id` is optional, so fall back to a
    /// composite key (mirrors `EntityCitationUsage.id`) to keep selection and
    /// `ForEach` stable even before ids are assigned.
    var id: String {
        citation.id ?? [
            direction.rawValue,
            citation.sourceDocumentId,
            citation.targetCitationText,
            citation.pageLabel ?? ""
        ].joined(separator: "|")
    }

    static func == (lhs: CitationItem, rhs: CitationItem) -> Bool { lhs.id == rhs.id }
    func hash(into hasher: inout Hasher) { hasher.combine(id) }
}

/// The citation identity shared by native drag sources and drop destinations.
/// Plain text keeps drops useful in editors and other applications.
struct CitationDragID: Codable, Transferable {
    let id: String
    let sourceDocumentId: String
    let targetDocumentId: String?
    let text: String

    static var transferRepresentation: some TransferRepresentation {
        CodableRepresentation(contentType: .json)
        ProxyRepresentation(exporting: \.text)
    }
}

/// Shared selection holder for the citations List + detail (#2004, EPIC #2002).
///
/// A per-domain copy of `FocusedArtifact`: the list writes the selected
/// citation id; the inline detail *and* the torn-off `CitationDetailWindow`
/// observe it. `CitationItem.shared` mirrors `FocusedArtifact.shared` so the
/// detached scene can follow the inspector's selection by reading one value —
/// no environment plumbing into a separate scene.
@Observable
@MainActor
final class FocusedCitation {
    /// Process-wide shared selection, referenced by both the inspector pane and
    /// the detached detail window.
    static let shared = FocusedCitation()

    /// The selected citation id (the `CitationItem.id`). Bound to
    /// `List(selection:)`; `nil` when nothing is selected.
    var id: String?

    /// The resolved item for `id`, kept in sync by the owning list pane — a
    /// value snapshot so the window can render without the store.
    private(set) var item: CitationItem?

    /// Human label for the document the selection belongs to — the detached
    /// window's subtitle.
    var documentName: String?

    init() {}

    /// Set the selection and resolve its snapshot against `items`.
    func select(_ id: String?, in items: [CitationItem]) {
        self.id = id
        resolve(in: items)
    }

    /// Re-resolve the snapshot for the current `id` against fresh `items`.
    func resolve(in items: [CitationItem]) {
        item = id.flatMap { selectedId in items.first { $0.id == selectedId } }
    }

    /// Clear the selection (e.g. on document switch).
    func clear() {
        id = nil
        item = nil
    }
}
