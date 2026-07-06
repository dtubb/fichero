import Foundation
import Observation

/// Shared selection holder for the artifact List + detail (#2003, EPIC #2002).
///
/// The list writes the selected artifact id; the detail (inline popover/pane
/// *and* the torn-off window) observes it. A single shared instance —
/// `FocusedArtifact.shared`, mirroring `KGFocusState.shared` /
/// `ClaimFocusState.shared` — is what lets a detached `WindowGroup` scene
/// follow the inspector's selection without re-plumbing environment objects
/// into a separate scene.
///
/// It carries both the `id` (so `List(selection:)` can bind to it) and a
/// resolved `artifact` *snapshot*. The snapshot means a downstream consumer
/// (the detached window) can render the selected artifact by reading one value
/// — it doesn't need access to the `ArtifactStore`. The list pane, which owns
/// the store, keeps the snapshot in sync via `select(_:in:)`.
///
/// This is the proving-ground shape that citations (#2004) and references
/// (#2005) will copy — a small id-plus-snapshot focus holder per domain.
@Observable
@MainActor
final class FocusedArtifact {
    /// Process-wide shared selection. The inspector pane and the detached
    /// detail window both reference this instance so the window follows what's
    /// selected in the inspector.
    static let shared = FocusedArtifact()

    /// The selected artifact id. Bound directly to `List(selection:)`. `nil`
    /// when nothing is selected (the detail shows its empty state).
    var id: String?

    /// The resolved artifact for `id`, kept in sync by the owning list pane.
    /// A value snapshot so a window can render it without the store.
    private(set) var artifact: Artifact?

    /// Human label for the document the selection belongs to — used as the
    /// detached window's subtitle so several torn-off windows are tellable
    /// apart.
    var documentName: String?

    init() {}

    /// Set the selection and resolve its snapshot against `items`. Called by
    /// the list pane whenever the selection changes or the store's items
    /// reload (so the snapshot tracks live edits / workflow re-runs).
    func select(_ id: String?, in items: [Artifact]) {
        self.id = id
        resolve(in: items)
    }

    /// Re-resolve the snapshot for the current `id` against fresh `items`.
    /// Keeps a torn-off window's content current when the store reloads
    /// without the selection itself changing.
    func resolve(in items: [Artifact]) {
        artifact = id.flatMap { selectedId in items.first { $0.id == selectedId } }
    }

    /// Clear the selection (e.g. on document switch).
    func clear() {
        id = nil
        artifact = nil
    }
}
