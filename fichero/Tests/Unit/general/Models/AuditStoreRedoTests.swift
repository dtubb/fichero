@testable import Fichero
import FicheroAPIClient
import Testing

/// #4700-class bug (menu audit 2026-09-17): `RedoLastActionButton` reversed a
/// redo target with the same `undo(_:)` call as any other row, which writes a
/// THIRD audit row that is itself `inverseOf`-set and not yet undone — a naive
/// "any untouched inverse" filter offered that third row back as a further
/// "redo", so a second ⌘⇧Z undid the redo it just performed instead of being
/// a no-op. `AuditStore.nextRedoable(in:)` is the pure fix: only an inverse of
/// a genuine FORWARD action (not an inverse of another inverse) counts.
@Suite("AuditStore redo walk")
struct AuditStoreRedoTests {

    private static func entry(
        _ id: String,
        undone: Bool,
        inverseOf: String? = nil,
        undoable: Bool = true
    ) -> Components.Schemas.AuditLogEntry {
        Components.Schemas.AuditLogEntry(
            id: id,
            actionName: "entity.merge",
            actor: "dtubb@me.com",
            client: nil,
            targetIds: ["t1"],
            createdAt: "2026-09-17T00:00:00Z",
            undone: undone,
            inverseOf: inverseOf,
            undoable: undoable
        )
    }

    @Test("press undo, then redo, then redo again — the second redo is a no-op, not an undo")
    func secondRedoIsANoOp() {
        // A: the original forward action.
        let a = Self.entry("A", undone: true)  // undone by B
        // B: ⌘Z's inverse of A — a genuine redo target while untouched.
        let b = Self.entry("B", undone: false, inverseOf: "A")

        // Before any redo: B is the (only) redo target.
        #expect(AuditStore.nextRedoable(in: [b, a])?.id == "B")

        // Redo #1 reverses B, which the store models as: B becomes undone,
        // and a new row C (inverse of B) is appended — the reapplied forward
        // action, structurally an "inverse" itself.
        let bAfterRedo = Self.entry("B", undone: true, inverseOf: "A")
        let c = Self.entry("C", undone: false, inverseOf: "B")
        let afterFirstRedo = [c, bAfterRedo, a]

        // The bug: C also has inverseOf != nil, undoable, not undone — a naive
        // filter would offer it as a further "redo" target. The fix must not.
        #expect(
            AuditStore.nextRedoable(in: afterFirstRedo) == nil,
            "after one redo, nothing is left to redo — offering C would let a second ⌘⇧Z undo the redo"
        )
    }

    @Test("an inverse of a forward action is a valid redo target")
    func inverseOfForwardActionIsRedoable() {
        let a = Self.entry("A", undone: true)
        let b = Self.entry("B", undone: false, inverseOf: "A")
        #expect(AuditStore.nextRedoable(in: [b, a])?.id == "B")
    }

    @Test("an already-undone or non-undoable inverse is never offered")
    func excludesUndoneAndNonUndoable() {
        let a = Self.entry("A", undone: true)
        let undoneInverse = Self.entry("B", undone: true, inverseOf: "A")
        #expect(AuditStore.nextRedoable(in: [undoneInverse, a]) == nil)

        let nonUndoableInverse = Self.entry("B2", undone: false, inverseOf: "A", undoable: false)
        #expect(AuditStore.nextRedoable(in: [nonUndoableInverse, a]) == nil)
    }
}
