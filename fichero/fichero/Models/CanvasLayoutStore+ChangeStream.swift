import Foundation

// MARK: - ObservableDomainStore (#3082)

/// Puts canvas *positions* on the library change stream: a `canvas.*` event
/// from another window/device reloads the affected scope so a move made
/// elsewhere lands here too — the cross-device half of "move it in a 2D
/// window, it moves in the 3D window" (same-device windows already share this
/// one instance and update live without the stream). Registered on
/// `LibraryReference` alongside the other stores (see `LibraryManager.changeStream`).
///
/// Kept in its own extension file (matching `DocumentStore+ChangeStream`) so the
/// core `CanvasLayoutStore.swift` stays focused on transport.
extension CanvasLayoutStore: ObservableDomainStore {
    nonisolated var changeDomain: String { "canvas" }

    /// Reconnect resync (`resync()` → `reload()`) and the change-event refetch:
    /// re-fetch every currently-loaded scope. Idempotent per scope, so an
    /// overlapping in-flight load is skipped.
    func reload() async {
        for scopeId in Array(layouts.keys) {
            await loadLayout(folderId: scopeId)
        }
    }

    /// Apply one `canvas.*` change event.
    ///
    /// ponytail: the backend canvas emit (#3078) does not yet carry scope + item
    /// ids on `ChangeEvent`, so a `canvas.layout.saved` from another device can't
    /// be spliced per-row here — reload the loaded scopes instead, debounced so
    /// an event storm coalesces into a single refetch (#1973). Own-window echoes
    /// are already dropped upstream by `LibraryChangeStream.route` (originWindow).
    /// Upgrade to a granular in-place splice once the emit payload includes the
    /// scope + item ids (#3082 step 4 → #3078 follow-up).
    func apply(_ event: ChangeEvent) {
        scheduleReload()
    }
}
