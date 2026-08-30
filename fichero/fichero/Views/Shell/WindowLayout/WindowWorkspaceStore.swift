import Foundation
import Observation

/// App-wide persistence for saved window workspaces (Daniel, 2026-08-29).
///
/// UserDefaults JSON, the same idiom the per-folder view-mode map uses
/// (`folderViewDisplayModesJSON`) — a small catalog, not a document. The
/// store is app-wide; APPLYING a workspace is per window
/// (`ContentView.applyLayoutSnapshot`).
@MainActor
@Observable
final class WindowWorkspaceStore {
    static let shared = WindowWorkspaceStore()
    static let defaultsKey = "window.workspaces"

    private let defaults: UserDefaults
    private(set) var catalog: WindowWorkspaceCatalog

    init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
        if let data = defaults.data(forKey: Self.defaultsKey),
           let decoded = WindowWorkspaceCatalog.decoded(from: data) {
            catalog = decoded
        } else {
            catalog = WindowWorkspaceCatalog()
        }
    }

    @discardableResult
    func save(name: String, layout: WindowLayoutSnapshot) -> SavedWindowWorkspace? {
        let saved = catalog.save(name: name, layout: layout)
        persist()
        return saved
    }

    func remove(id: UUID) {
        catalog.remove(id: id)
        persist()
    }

    private func persist() {
        // A catalog of value types with these fields cannot fail to encode in
        // practice; if it ever does, keeping the previous stored value beats
        // wiping the user's saved layouts (prefer-raise rule does not apply to
        // a best-effort cache of user chrome, and there is no id substitution).
        guard let data = try? catalog.encoded() else { return }
        defaults.set(data, forKey: Self.defaultsKey)
    }
}
