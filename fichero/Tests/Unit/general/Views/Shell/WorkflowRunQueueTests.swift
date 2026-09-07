//
//  WorkflowRunQueueTests.swift
//  FicheroTests
//
//  The workflow bar can now launch a run and then compose the next one while
//  it executes (Daniel, 2026-09-07: "start a run and compose the next thing,
//  e.g. do Apple Vision, then do Google"). Runs launched while another is still
//  executing are ENQUEUED and drained in order. These cover the pure queue:
//  enqueue-while-running order, FIFO drain, an empty queue leaving the
//  single-run path untouched, and removing a still-pending run.
//

@testable import Fichero
import Foundation
import Testing

struct WorkflowRunQueueTests {

    private func step(id: String, name: String) -> StagedWorkflowStep {
        StagedWorkflowStep(kind: .workflow(WorkflowSidebarItem(id: id, name: name)))
    }

    private func run(
        _ name: String, docIds: [String] = ["doc-1"], context: String = ""
    ) -> QueuedWorkflowRun {
        QueuedWorkflowRun(
            steps: [step(id: "wf-\(name)", name: name)],
            scope: .documents(ids: docIds),
            userContext: context
        )
    }

    // MARK: - Empty queue = single-run behavior, untouched

    @Test("a fresh queue is empty and offers nothing to drain")
    func emptyQueueDrainsToNil() {
        var queue = WorkflowRunQueue()
        #expect(queue.isEmpty)
        #expect(queue.count == 0)
        #expect(queue.nextTitle == nil)
        // Dequeue on an empty queue is a no-op returning nil, so the host's
        // drain check after a lone run finds nothing and the bar stays in its
        // single-run resting state.
        #expect(queue.dequeue() == nil)
        #expect(queue.isEmpty)
    }

    // MARK: - Enqueue while running → drain in order

    @Test("runs launched while one executes drain in the order they were launched")
    func enqueueWhileRunningDrainsFIFO() {
        var queue = WorkflowRunQueue()
        // The user launches Apple Vision (executes immediately, not queued),
        // then composes and launches Google, then Whisper — both enqueued
        // because a run is already in flight.
        queue.enqueue(run("Google"))
        queue.enqueue(run("Whisper"))

        #expect(queue.count == 2)
        #expect(queue.nextTitle == "Google")

        // Apple Vision finishes → the host drains the next: Google first.
        let first = queue.dequeue()
        #expect(first?.title == "Google")
        #expect(queue.count == 1)
        #expect(queue.nextTitle == "Whisper")

        // Google finishes → Whisper.
        let second = queue.dequeue()
        #expect(second?.title == "Whisper")
        #expect(queue.isEmpty)

        // Whisper finishes → nothing left; the bar returns to single-run rest.
        #expect(queue.dequeue() == nil)
    }

    @Test("a queued run freezes its steps, scope and context at launch")
    func queuedRunFreezesLaunchInputs() {
        var queue = WorkflowRunQueue()
        queue.enqueue(run("Google", docIds: ["a", "b"], context: "diary"))
        let drained = queue.dequeue()
        #expect(drained?.scope == .documents(ids: ["a", "b"]))
        #expect(drained?.userContext == "diary")
        #expect(drained?.steps.map(\.name) == ["Google"])
    }

    // MARK: - Title derivation

    @Test("a multi-step run names its head plus a count")
    func multiStepRunTitle() {
        let queued = QueuedWorkflowRun(
            steps: [
                step(id: "wf-1", name: "Transcribe"),
                step(id: "wf-2", name: "Clean up"),
                step(id: "wf-3", name: "Catalogue")
            ],
            scope: .documents(ids: ["doc-1"]),
            userContext: ""
        )
        #expect(queued.title == "Transcribe +2")
    }

    @Test("a single-step run is named for that step alone")
    func singleStepRunTitle() {
        #expect(run("Transcribe").title == "Transcribe")
    }

    // MARK: - Remove a still-pending run

    @Test("removing a pending run drops only it and preserves order")
    func removePendingRun() {
        var queue = WorkflowRunQueue()
        let google = run("Google")
        let whisper = run("Whisper")
        let translate = run("Translate")
        queue.enqueue(google)
        queue.enqueue(whisper)
        queue.enqueue(translate)

        queue.remove(whisper.id)
        #expect(queue.count == 2)
        #expect(queue.dequeue()?.id == google.id)
        #expect(queue.dequeue()?.id == translate.id)
    }

    @Test("removing an unknown id leaves the queue unchanged")
    func removeUnknownIsNoOp() {
        var queue = WorkflowRunQueue()
        queue.enqueue(run("Google"))
        queue.remove(UUID())
        #expect(queue.count == 1)
    }

    @Test("clear discards every pending run")
    func clearEmptiesQueue() {
        var queue = WorkflowRunQueue()
        queue.enqueue(run("Google"))
        queue.enqueue(run("Whisper"))
        queue.clear()
        #expect(queue.isEmpty)
        #expect(queue.dequeue() == nil)
    }
}
