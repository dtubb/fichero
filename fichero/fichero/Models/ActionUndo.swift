import Foundation
import OSLog

/// ⌘Z and ⇧⌘Z for an audited engine action, through the system `UndoManager`
/// (`source.editor.system-undo`, #4941). The core of the one helper, `UndoableChange` (#5658):
/// nothing else registers a project step.
///
/// The engine already inverts any audited action (`POST /api/actions/audit/{id}/undo`, and as a
/// set, `POST /api/actions/audit/undo`) and redo is the undo of the undo. What the app lacked was
/// the id: reading the newest audit row instead would have been a race against any other writer —
/// on a shared library, one person undoing another's edit.
///
/// THE ONE SUBTLETY, and the reason this is a type rather than three lines at each call
/// site. `UndoManager` records a registration made WHILE it is undoing as a REDO. The
/// engine call is async, so its answer — the inverse rows' own audit ids, which are
/// what the redo must invert — arrives after the undo handler has returned, when
/// registering would record a new UNDO instead and ⇧⌘Z would do nothing. So the redo is
/// registered SYNCHRONOUSLY inside the handler, holding a box the async call fills in.
/// A redo pressed before the engine answered finds the box empty and does nothing,
/// logged, rather than inverting the wrong row.
///
/// A step holds a SET of rows (`undo.batches.whole`): a batch of N changes is one step, reversed by
/// one engine call, all or none. When the engine refuses, `onRefusal` is told, the redo filed for
/// the refused reversal is taken off again, and a refused UNDO whose reason keeps the step
/// (`changed`) is put back on the stack as it was.
@MainActor
enum ActionUndo {
    private static let logger = Logger(subsystem: "app.fichero.fichero", category: "ActionUndo")

    /// Holds the audit ids a pending undo will produce, so the redo can be registered
    /// before the ids exist. `pending` is exposed for tests to await.
    final class Handle {
        var auditIds: [String]?
        var pending: Task<Void, Never>?
        init(auditIds: [String]?) { self.auditIds = auditIds }
        convenience init(auditId: String?) { self.init(auditIds: auditId.map { [$0] }) }
        /// The one row of a single-row step.
        var auditId: String? { auditIds?.first }
    }

    /// What a step does around its engine calls: count them (Undo and Redo wait while one is out,
    /// `undo.window.in-flight`), remember its handles (so a project's steps can end), and hear a
    /// refusal (so the window shows the engine's sentence).
    struct Hooks {
        var willCall: @MainActor () -> Void = {}
        var didCall: @MainActor () -> Void = {}
        var didRegister: @MainActor (Handle) -> Void = { _ in }
        var onRefusal: @MainActor (Error) -> Void = { _ in }
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
        guard let auditId, !auditId.isEmpty else { return nil }
        return registerSet(
            auditIds: [auditId], actionName: actionName, undoManager: undoManager,
            performUndo: { ids in [try await performUndo(ids[0])] }
        )
    }

    /// The core: one step holding `auditIds`, reversed as a set by `performUndo`, which answers the
    /// rows its reversal wrote.
    @discardableResult
    static func registerSet(
        auditIds: [String],
        actionName: String,
        undoManager: UndoManager?,
        hooks: Hooks = Hooks(),
        performUndo: @escaping @MainActor ([String]) async throws -> [String]
    ) -> Handle? {
        let ids = auditIds.filter { !$0.isEmpty }
        guard let undoManager, !ids.isEmpty else { return nil }
        let handle = Handle(auditIds: ids)
        schedule(handle, actionName: actionName, undoManager: undoManager, hooks: hooks, performUndo: performUndo)
        return handle
    }

    private static func schedule(
        _ handle: Handle,
        actionName: String,
        undoManager: UndoManager,
        hooks: Hooks,
        performUndo: @escaping @MainActor ([String]) async throws -> [String]
    ) {
        // A registration outside any group is refused by an UndoManager that does not group by
        // event (the window's own stack); inside an undo or redo the manager has its group open.
        let opensGroup = undoManager.groupingLevel == 0 && !undoManager.groupsByEvent
        if opensGroup { undoManager.beginUndoGrouping() }
        defer { if opensGroup { undoManager.endUndoGrouping() } }
        // The closure holds `handle` STRONGLY, and it must. UndoManager does not retain its
        // target: with only `current` (the target, passed back) the handle was freed as soon
        // as `register` returned -- the app's one caller discards it, `@discardableResult` --
        // and the first ⌘Z crashed inside `-[NSUndoManager undoNestedGroup]` on a dangling
        // object (SIGTRAP, `swift_getObjectType`). Captured here, the handle lives exactly
        // as long as the undo entry does. Found by ActionUndoTests on first execution.
        undoManager.registerUndo(withTarget: handle) { _ in
            let current = handle
            MainActor.assumeIsolated {
                let wasUndo = !undoManager.isRedoing
                // Registered NOW, inside the handler, so UndoManager files it as the redo
                // of this undo. Its ids are filled in when the engine answers.
                let next = Handle(auditIds: nil)
                schedule(next, actionName: actionName, undoManager: undoManager, hooks: hooks,
                         performUndo: performUndo)

                guard let target = current.auditIds else {
                    // The previous step's engine call has not answered yet (or failed), so
                    // there is no row to invert. Doing nothing is the only safe answer:
                    // guessing a row is how one person undoes another's edit.
                    logger.notice("\(actionName, privacy: .public): pressed before the engine answered; nothing done")
                    return
                }
                hooks.willCall()
                next.pending = Task { @MainActor in
                    defer { hooks.didCall() }
                    do {
                        next.auditIds = try await performUndo(target)
                    } catch {
                        // The reversal did not happen: the step filed for it reverses nothing.
                        undoManager.removeAllActions(withTarget: next)
                        let keeps = (error as? UndoRefusal)?.keepsTheStep ?? true
                        if keeps && wasUndo {
                            // `changed` (or no answer at all): the step stays where it was.
                            schedule(current, actionName: actionName, undoManager: undoManager, hooks: hooks,
                                     performUndo: performUndo)
                        }
                        // ponytail: a refused REDO cannot go back on the redo stack (a registration
                        // outside a handler is an undo); it is dropped, and the history list still has it.
                        logger.error("\(actionName, privacy: .public): refused — \(error.localizedDescription, privacy: .public)")
                        hooks.onRefusal(error)
                    }
                }
            }
        }
        undoManager.setActionName(actionName)
        hooks.didRegister(handle)
    }
}
