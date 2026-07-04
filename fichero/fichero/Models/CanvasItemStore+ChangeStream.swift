import Foundation

// MARK: - ObservableDomainStore (#3082)

/// Puts standalone canvas item *content* on the library change stream — the
/// sibling of `CanvasLayoutStore+ChangeStream` for the note/quote/text/link
/// bodies. A `canvas.*` event from another window/device reloads the affected
/// scope. Registered on `LibraryReference` (see `LibraryManager.changeStream`).
extension CanvasItemStore: ObservableDomainStore {
    nonisolated var changeDomain: String { "canvas" }

    /// Reconnect resync + change-event refetch: re-fetch every currently-loaded
    /// scope (idempotent per scope).
    func reload() async {
        for scopeId in Array(itemsByScope.keys) {
            await loadItems(folderId: scopeId)
        }
    }

    /// Apply one `canvas.*` change event.
    ///
    /// ponytail: same as `CanvasLayoutStore.apply` — the backend emit (#3078)
    /// carries no scope/item ids on `ChangeEvent` yet, so reload the loaded
    /// scopes (debounced); own-window echoes are dropped upstream. Granular
    /// per-row splice awaits the emit payload (#3082 step 4 → #3078 follow-up).
    func apply(_ event: ChangeEvent) {
        scheduleReload()
    }
}
