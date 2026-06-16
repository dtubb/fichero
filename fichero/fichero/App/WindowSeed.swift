import Foundation

/// Serializable snapshot used to seed a NEW library window with the same
/// library + selection + active lens as an existing one — the payload behind
/// the **Duplicate Window** command (#2262, reform master plan §J).
///
/// It carries only simple `Codable` values (the very same per-window state
/// #2273 persists via `@SceneStorage`: the open library, the sidebar selection,
/// and the active view-mode / lens) so it can ride `openWindow(value:)` and
/// SwiftUI scene restoration. `LibraryWindow` consumes a seed on launch by
/// writing these into its `@SceneStorage` keys *before* the content mounts, so
/// `ContentView.restorePersistedState()` restores the cloned state on appear.
struct WindowSeed: Codable, Hashable {
    /// The library this window views (UUID string — matches `LibraryManager` ids).
    let libraryId: String

    /// On-disk path of the library, used as a fallback to re-open it if the
    /// duplicated window is restored after the source library was closed.
    /// `nil` for unsaved / temporary libraries.
    let libraryPath: String?

    /// Persisted sidebar selection (the `selectedSidebarItem` scene-storage key).
    let selectedItemId: String?

    /// Active lens / view-mode (the `viewModeType` scene-storage key).
    let viewModeType: String?

    /// Item the active lens is scoped to (the `viewModeItemId` scene-storage key).
    let viewModeItemId: String?
}
