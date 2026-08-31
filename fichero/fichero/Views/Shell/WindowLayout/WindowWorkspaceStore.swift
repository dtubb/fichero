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
    static let toolbarDefaultsKey = "window.toolbarVisibility"

    private let defaults: UserDefaults
    private(set) var catalog: WindowWorkspaceCatalog

    /// Which optional toolbar buttons show (Daniel, 2026-08-31). APP-WIDE, not
    /// per window, because that is what a Mac toolbar configuration is: AppKit
    /// keys an `NSToolbar`'s customisation to the toolbar's identifier, so every
    /// window of a kind shares it. Keeping it here also keeps `ContentView`'s
    /// value size flat (ViewValueSizeTests' ratchet) — four more @SceneStorage
    /// wrappers on the view would have blown the ceiling the comment there
    /// tells us to box rather than raise.
    private(set) var toolbarVisibility: ToolbarVisibilityPlan

    init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
        if let data = defaults.data(forKey: Self.defaultsKey),
           let decoded = WindowWorkspaceCatalog.decoded(from: data) {
            catalog = decoded
        } else {
            catalog = WindowWorkspaceCatalog()
        }
        if let data = defaults.data(forKey: Self.toolbarDefaultsKey),
           let decoded = try? JSONDecoder().decode(ToolbarVisibilityPlan.self, from: data) {
            toolbarVisibility = decoded
        } else {
            toolbarVisibility = .everything
        }
    }

    /// Set the toolbar configuration — from the Workspaces menu's own toggles,
    /// or from a workspace being applied.
    func setToolbarVisibility(_ plan: ToolbarVisibilityPlan) {
        guard plan != toolbarVisibility else { return }
        toolbarVisibility = plan
        persistToolbarVisibility()
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

    private func persistToolbarVisibility() {
        // Best-effort, same reasoning as `persist()`: keeping the previous
        // stored configuration beats wiping the user's toolbar.
        guard let data = try? JSONEncoder().encode(toolbarVisibility) else { return }
        defaults.set(data, forKey: Self.toolbarDefaultsKey)
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
