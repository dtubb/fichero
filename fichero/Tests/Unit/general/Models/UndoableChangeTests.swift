@testable import Fichero
import Foundation
import Testing

/// The one helper (`UndoableChange`) and the window's step stack (`WindowSteps`), #5658, ruled per window
/// 2026-10-11: a step is the rows a change wrote, named in words; undo and redo take the rows back as a set
/// through the project's live service; a refusal is shown and keeps or drops the step by its reason; Undo
/// and Redo wait while a call is out. Driven against a fake engine with a REAL UndoManager, because what
/// breaks is UndoManager's own bookkeeping across the async engine call.
@MainActor
struct UndoableChangeTests {
    /// A fake engine for one project: it records each set it is asked to take back and answers new rows
    /// ("u1", "u2", …); it can refuse, and it can hold its answer until released.
    @MainActor
    final class FakeEngine: UndoSetEngine {
        let projectPath: String?
        var sets: [[String]] = []
        var refusal: UndoRefusal?
        var holds = false
        private var held: [CheckedContinuation<Void, Never>] = []
        private var counter = 0

        init(_ path: String = "/tmp/P.fichero") { projectPath = path }

        func undoSet(auditIds: [String]) async throws -> [String] {
            sets.append(auditIds)
            if holds { await withCheckedContinuation { held.append($0) } }
            if let refusal { throw refusal }
            return auditIds.map { _ in counter += 1; return "u\(counter)" }
        }

        func release() {
            holds = false
            held.forEach { $0.resume() }
            held = []
        }
    }

    /// Wait for the window's calls to come back.
    private func settle(_ steps: WindowSteps) async {
        for _ in 0..<500 where steps.inFlight > 0 { try? await Task.sleep(nanoseconds: 2_000_000) }
        for _ in 0..<5 { await Task.yield() }
    }

    @Test("a change is one step, named in words; the menu reads its name")
    func aStepIsNamed() {
        let steps = WindowSteps()
        steps.register(["a1"], named: "Move", engine: FakeEngine())
        #expect(steps.canUndo)
        #expect(steps.undoName == "Move")
        #expect(UndoableChange.register([], named: "Nothing", service: FakeEngine(), steps: steps) == nil,
                "no rows: nothing to take back, no step")
        #expect(UndoableChange.register(["a2"], named: "No window", service: FakeEngine(), steps: nil) == nil)
    }

    @Test("a step over several things counts them (undo.naming.counts)")
    func namesCount() {
        #expect(UndoableChange.named("Delete", count: 1, one: "Note", many: "Items") == "Delete Note")
        #expect(UndoableChange.named("Delete", count: 3, one: "Note", many: "Items") == "Delete 3 Items")
    }

    @Test("a batch is ONE step, undone as one set, and its redo takes back the rows the undo wrote")
    func aBatchIsOneSet() async throws {
        let steps = WindowSteps()
        let engine = FakeEngine()
        try await UndoableChange.batch(
            ["n1", "n2", "n3"], named: { UndoableChange.named("Delete", count: $0, one: "Note", many: "Notes") },
            service: engine, steps: steps, change: { note in ["row-\(note)"] }
        )
        #expect(steps.undoName == "Delete 3 Notes")

        steps.undo()
        await settle(steps)
        #expect(engine.sets == [["row-n1", "row-n2", "row-n3"]], "all three in one call")
        #expect(!steps.canUndo)
        #expect(steps.redoName == "Delete 3 Notes")

        steps.redo()
        await settle(steps)
        #expect(engine.sets.last == ["u1", "u2", "u3"], "the redo takes back the rows the undo wrote")
        #expect(steps.canUndo)
    }

    @Test("a batch that failed part way holds only what was written, counted")
    func aFailedBatchHoldsWhatWasWritten() async {
        let steps = WindowSteps()
        struct Refused: Error {}
        await #expect(throws: Refused.self) {
            try await UndoableChange.batch(
                ["n1", "n2", "n3"], named: { UndoableChange.named("Delete", count: $0, one: "Note", many: "Notes") },
                service: FakeEngine(), steps: steps,
                change: { note in
                    if note == "n3" { throw Refused() }
                    return ["row-\(note)"]
                }
            )
        }
        #expect(steps.undoName == "Delete 2 Notes")
    }

    @Test("a `changed` refusal keeps the step, and the window shows the engine's sentence")
    func changedKeepsTheStep() async {
        let steps = WindowSteps()
        let engine = FakeEngine()
        engine.refusal = UndoRefusal(sentence: "This note was changed in another window at 14:02.", reason: .changed)
        steps.register(["a1"], named: "Rename", engine: engine)

        steps.undo()
        await settle(steps)
        #expect(steps.refusal == "This note was changed in another window at 14:02.")
        #expect(steps.canUndo, "the step is still offered")
        #expect(steps.undoName == "Rename")
        #expect(!steps.canRedo, "nothing was taken back, so there is nothing to put back")

        engine.refusal = nil
        steps.undo()
        await settle(steps)
        #expect(engine.sets == [["a1"], ["a1"]], "the same rows, asked again")
    }

    @Test("`already-undone` and `gone` drop the step, with the sentence")
    func alreadyUndoneAndGoneDrop() async {
        for reason in [UndoRefusal.Reason.alreadyUndone, .gone] {
            let steps = WindowSteps()
            let engine = FakeEngine()
            engine.refusal = UndoRefusal(sentence: "This change was already taken back in another window.", reason: reason)
            steps.register(["a1"], named: "Move", engine: engine)
            steps.undo()
            await settle(steps)
            #expect(steps.refusal == "This change was already taken back in another window.")
            #expect(!steps.canUndo, "\(reason): dropped")
            #expect(!steps.canRedo)
        }
    }

    @Test("Undo and Redo wait while a call is out (undo.window.in-flight)")
    func inFlightDisables() async {
        let steps = WindowSteps()
        let engine = FakeEngine()
        steps.register(["a1"], named: "Move", engine: engine)
        engine.holds = true
        steps.undo()
        for _ in 0..<50 where engine.sets.isEmpty { await Task.yield() }
        #expect(steps.inFlight == 1)
        #expect(!steps.canUndo && !steps.canRedo, "a quick ⌘Z or ⇧⌘Z now would act on the wrong step")
        engine.release()
        await settle(steps)
        #expect(steps.canRedo)
    }

    @Test("a change still running holds Undo back, so the step before it is never taken back")
    func aRunningChangeHoldsUndo() async throws {
        let steps = WindowSteps()
        let engine = FakeEngine()
        steps.register(["a1"], named: "Move", engine: engine)
        try await UndoableChange.run(named: "Rename", service: engine, steps: steps, {
            #expect(!steps.canUndo, "while the rename is out, Undo is off")
            return "a2"
        }, auditIds: { [$0] })
        #expect(steps.undoName == "Rename")
    }

    @Test("a redo pressed before the undo's answer does nothing (undo.redo.before-the-answer)")
    func redoBeforeTheAnswer() async {
        let steps = WindowSteps()
        let engine = FakeEngine()
        steps.register(["a1"], named: "Move", engine: engine)
        engine.holds = true
        steps.undo()
        for _ in 0..<50 where engine.sets.isEmpty { await Task.yield() }
        steps.undoManager.redo()   // straight to the stack: the menu itself would be disabled
        for _ in 0..<20 { await Task.yield() }
        #expect(engine.sets.count == 1, "no row is guessed")
        engine.release()
        await settle(steps)
    }

    @Test("a new step clears Redo (undo.redo.new-step-clears)")
    func newStepClearsRedo() async {
        let steps = WindowSteps()
        let engine = FakeEngine()
        steps.register(["a1"], named: "Move", engine: engine)
        steps.undo()
        await settle(steps)
        #expect(steps.canRedo)
        steps.register(["a2"], named: "Rename", engine: engine)
        #expect(!steps.canRedo)
    }

    @Test("ending one project's steps leaves the other's (undo.steps-end)")
    func endingOneProjectsSteps() {
        let steps = WindowSteps()
        steps.register(["p1"], named: "Move", engine: FakeEngine("/tmp/P.fichero"))
        steps.register(["q1"], named: "Rename", engine: FakeEngine("/tmp/Q.fichero"))
        steps.endSteps(forProject: "/tmp/Q.fichero")
        #expect(steps.undoName == "Move", "Q's step is gone, P's is next")
        steps.endAllSteps()
        #expect(!steps.canUndo, "a sign-out empties the stack")
    }

    @Test("the project's live service is looked up at undo time (undo.engine-restart)")
    func liveServiceAtUndoTime() async {
        let steps = WindowSteps()
        let before = FakeEngine()
        let after = FakeEngine()
        steps.register(["a1"], named: "Move", engine: before)
        steps.engineForProject = { _ in after }   // the engine restarted; the project has a new service
        steps.undo()
        await settle(steps)
        #expect(before.sets.isEmpty)
        #expect(after.sets == [["a1"]])
    }

    @Test("the same rows answered again are the step already on top (undo.typing.commit-is-one-step)")
    func sameRowsCoalesce() async {
        let steps = WindowSteps()
        let engine = FakeEngine()
        steps.register(["a1"], named: "Edit Transcription", engine: engine)
        steps.register(["a1"], named: "Edit Transcription", engine: engine)
        steps.undo()
        await settle(steps)
        #expect(!steps.canUndo, "one step, not two")
    }
}
