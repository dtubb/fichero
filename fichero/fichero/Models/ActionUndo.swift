import Foundation

/// ⌘Z and ⇧⌘Z for an audited engine action, through the system `UndoManager`
/// (`source.editor.system-undo`, #4941).
///
/// The engine already inverts any audited action (`POST /api/actions/audit/{id}/undo`)
/// and redo is the undo of the undo. What the app lacked was the id: a region edit now
/// answers its `audit_id` (`ArtifactRegionsEditResponse`, synced into the client in
/// c88c97763), and reading the newest audit row instead would have been a race against
/// any other writer — on a shared library, one person undoing another's edit.
///
/// THE ONE SUBTLETY, and the reason this is a type rather than three lines at each call
/// site. `UndoManager` records a registration made WHILE it is undoing as a REDO. The
/// engine call is async, so its answer — the inverse action's own audit id, which is
/// what the redo must invert — arrives after the undo handler has returned, when
/// registering would record a new UNDO instead and ⇧⌘Z would do nothing. So the redo is
/// registered SYNCHRONOUSLY inside the handler, holding a box the async call fills in.
/// A redo pressed before the engine answered finds the box empty and does nothing,
/// logged, rather than inverting the wrong row.
@MainActor
enum ActionUndo {
    /// Holds the audit id a pending undo will produce, so the redo can be registered
    /// before the id exists. `pending` is exposed for tests to await.
    final class Handle {
        var auditId: String?
        var pending: Task<Void, Never>?
        init(auditId: String?) { self.auditId = auditId }
    }

    /// Register `auditId` for ⌘Z. `performUndo` asks the engine to invert an audit row
    /// and returns the NEW row the inversion wrote — which is what the next step (the
    /// redo, then the undo of that, and so on) inverts.
    ///
    /// Returns the handle so a caller or a test can see the chain; most callers ignore it.
    @discardableResult
    static func register(
        auditId: String?,
        actionName: String,
        undoManager: UndoManager?,
        performUndo: @escaping @MainActor (String) async throws -> String
    ) -> Handle? {
        guard let undoManager, let auditId, !auditId.isEmpty else { return nil }
        let handle = Handle(auditId: auditId)
        schedule(handle, actionName: actionName, undoManager: undoManager, performUndo: performUndo)
        return handle
    }

    private static func schedule(
        _ handle: Handle,
        actionName: String,
        undoManager: UndoManager,
        performUndo: @escaping @MainActor (String) async throws -> String
    ) {
        undoManager.registerUndo(withTarget: handle) { current in
            MainActor.assumeIsolated {
                // Registered NOW, inside the handler, so UndoManager files it as the redo
                // of this undo. Its id is filled in when the engine answers.
                let next = Handle(auditId: nil)
                schedule(next, actionName: actionName, undoManager: undoManager,
                         performUndo: performUndo)

                guard let target = current.auditId else {
                    // The previous step's engine call has not answered yet (or failed), so
                    // there is no row to invert. Doing nothing is the only safe answer:
                    // guessing a row is how one person undoes another's edit.
                    return
                }
                next.pending = Task { @MainActor in
                    next.auditId = try? await performUndo(target)
                }
            }
        }
        undoManager.setActionName(actionName)
    }
}
