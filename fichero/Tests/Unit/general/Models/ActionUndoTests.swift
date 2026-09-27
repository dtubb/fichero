@testable import Fichero
import Foundation
import Testing

/// `source.editor.system-undo` (#4941): ⌘Z and ⇧⌘Z through the system `UndoManager`,
/// inverting the engine's audited actions.
///
/// These drive a REAL `UndoManager` with a fake engine, because the thing that breaks is
/// `UndoManager`'s own bookkeeping: a registration made after an undo handler returns is
/// filed as a new undo, not a redo, and ⇧⌘Z silently does nothing. The engine call is
/// async, so the easy implementation registers too late.
@MainActor
struct ActionUndoTests {

    /// A fake engine that inverts `a1` into `a2`, `a2` into `a3`, and so on, recording
    /// what it was asked to invert.
    final class FakeEngine {
        var inverted: [String] = []
        private var counter = 1
        func undo(_ auditId: String) async throws -> String {
            inverted.append(auditId)
            counter += 1
            return "a\(counter)"
        }
    }

    private func manager() -> UndoManager {
        let manager = UndoManager()
        // Group by event is for run loops; a test drives undo directly.
        manager.groupsByEvent = false
        return manager
    }

    private func register(_ id: String?, on manager: UndoManager, engine: FakeEngine) -> ActionUndo.Handle? {
        manager.beginUndoGrouping()
        let handle = ActionUndo.register(
            auditId: id, actionName: "Move Region", undoManager: manager,
            performUndo: engine.undo
        )
        manager.endUndoGrouping()
        return handle
    }

    @Test("⌘Z inverts the action that was registered, by its own audit id")
    func undoInvertsTheRegisteredAction() async {
        let manager = manager()
        let engine = FakeEngine()
        let handle = register("a1", on: manager, engine: engine)

        #expect(manager.canUndo)
        manager.undo()
        // The redo registered inside the handler holds the pending engine call.
        await settle(manager)

        #expect(engine.inverted == ["a1"], "the edit's own row, never a guessed one")
        _ = handle
    }

    @Test("⇧⌘Z is available after ⌘Z — the redo was registered AS a redo")
    func redoIsRegisteredDuringTheUndo() async {
        // The whole subtlety: registering after the async call would file a new UNDO and
        // leave nothing to redo.
        let manager = manager()
        let engine = FakeEngine()
        _ = register("a1", on: manager, engine: engine)

        manager.undo()
        await settle(manager)

        #expect(manager.canRedo, "⇧⌘Z must be available after ⌘Z")
    }

    @Test("redo inverts the row the UNDO wrote, not the original")
    func redoInvertsTheUndosOwnRow() async {
        // Redo is the undo of the undo: the engine's undo of `a1` wrote `a2`, so redo must
        // invert `a2`. Replaying `a1` would be the stale-replay defect #4957 fixed on the
        // engine side, reintroduced in the app.
        let manager = manager()
        let engine = FakeEngine()
        _ = register("a1", on: manager, engine: engine)

        manager.undo()
        await settle(manager)
        manager.redo()
        await settle(manager)

        #expect(engine.inverted == ["a1", "a2"])
    }

    @Test("undo, redo, undo walks the chain one row at a time")
    func theChainKeepsGoing() async {
        let manager = manager()
        let engine = FakeEngine()
        _ = register("a1", on: manager, engine: engine)

        manager.undo(); await settle(manager)
        manager.redo(); await settle(manager)
        manager.undo(); await settle(manager)

        #expect(engine.inverted == ["a1", "a2", "a3"])
    }

    @Test("a DISCARDED handle still undoes — the app's caller throws it away")
    func discardedHandleStillUndoes() async {
        // The app registers and ignores the result (`@discardableResult`). UndoManager does
        // not retain its target, so if nothing else held the handle, ⌘Z invoked a freed
        // object and crashed Fichero. This test does exactly what the app does, nothing more.
        let manager = manager()
        let engine = FakeEngine()
        manager.beginUndoGrouping()
        ActionUndo.register(
            auditId: "a1", actionName: "Move Region", undoManager: manager,
            performUndo: engine.undo
        )
        manager.endUndoGrouping()

        manager.undo()
        await settle(manager)
        manager.redo()
        await settle(manager)

        #expect(engine.inverted == ["a1", "a2"], "undo and redo both reached the engine")
    }

    @Test("with no audit id, nothing is registered — there is no row to invert")
    func noAuditIdRegistersNothing() {
        // The route answers audit_id; if it ever comes back empty, offering ⌘Z would
        // mean inverting a guessed row.
        // Called WITHOUT the grouping helper: an empty begin/end grouping is itself an undo
        // entry to UndoManager (canUndo reads true with nothing registered), which is what the
        // first version of this test measured instead of ActionUndo.
        let manager = manager()
        let engine = FakeEngine()

        for empty in [String?.none, ""] {
            let handle = ActionUndo.register(
                auditId: empty, actionName: "Move Region", undoManager: manager,
                performUndo: engine.undo
            )
            #expect(handle == nil)
        }
        #expect(manager.canUndo == false)
    }

    @Test("with no undo manager, nothing happens and nothing crashes")
    func noUndoManagerIsHarmless() {
        let handle = ActionUndo.register(
            auditId: "a1", actionName: "Move Region", undoManager: nil,
            performUndo: FakeEngine().undo
        )
        #expect(handle == nil)
    }

    /// Wait for whatever engine call the last undo/redo started.
    private func settle(_ manager: UndoManager) async {
        // The pending task lives on the handle registered for the NEXT step; yielding a
        // few times lets it run to completion on the main actor.
        for _ in 0..<10 { await Task.yield() }
    }
}
