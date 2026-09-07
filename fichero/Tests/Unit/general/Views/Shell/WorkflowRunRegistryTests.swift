//
//  WorkflowRunRegistryTests.swift
//  FicheroTests
//
//  The workflow bar can launch a run and immediately compose the next, which
//  runs CONCURRENTLY (Daniel, 2026-09-07: "it stays in activity. not queued
//  behind vision. it can run in parallel. it lets us do one thing, then try
//  the next"). Runs launched while others execute do NOT wait — they run in
//  parallel, each tracked independently in Activity. These cover the pure
//  registry: launch registers, several run at once, and a finish (in any
//  order) removes only that run while the rest keep going.
//

@testable import Fichero
import Foundation
import Testing

struct WorkflowRunRegistryTests {

    private func step(id: String, name: String) -> StagedWorkflowStep {
        StagedWorkflowStep(kind: .workflow(WorkflowSidebarItem(id: id, name: name)))
    }

    private func run(
        _ name: String, docIds: [String] = ["doc-1"], context: String = ""
    ) -> ActiveWorkflowRun {
        ActiveWorkflowRun(
            steps: [step(id: "wf-\(name)", name: name)],
            scope: .documents(ids: docIds),
            userContext: context
        )
    }

    // MARK: - Empty registry = idle, single-run untouched

    @Test("a fresh registry is empty and idle")
    func emptyRegistryIsIdle() {
        let registry = WorkflowRunRegistry()
        #expect(registry.isEmpty)
        #expect(registry.count == 0)
        #expect(registry.latestTitle == nil)
    }

    // MARK: - Launch registers; runs are concurrent, not queued

    @Test("launching runs registers them all as concurrently running")
    func launchesRunConcurrently() {
        var registry = WorkflowRunRegistry()
        // Apple Vision launches and runs; Google launches while it is still
        // going — NOT queued behind it, both running at once.
        let vision = run("AppleVision")
        let google = run("Google")
        registry.register(vision)
        registry.register(google)

        // Both are running at the same time — the registry is not a queue.
        #expect(registry.count == 2)
        #expect(registry.run(vision.id) != nil)
        #expect(registry.run(google.id) != nil)
        // The compact status names the most recent launch when it collapses.
        #expect(registry.latestTitle == "Google")
    }

    @Test("a run finishing leaves every other concurrent run untouched")
    func finishOneKeepsTheRest() {
        var registry = WorkflowRunRegistry()
        let vision = run("AppleVision")
        let google = run("Google")
        let whisper = run("Whisper")
        registry.register(vision)
        registry.register(google)
        registry.register(whisper)
        #expect(registry.count == 3)

        // Google finishes first, though it launched second — parallel runs
        // settle in whatever order they complete, not launch order.
        registry.finish(google.id)
        #expect(registry.count == 2)
        #expect(registry.run(google.id) == nil)
        // Vision and Whisper keep running, undisturbed.
        #expect(registry.run(vision.id) != nil)
        #expect(registry.run(whisper.id) != nil)

        registry.finish(vision.id)
        registry.finish(whisper.id)
        #expect(registry.isEmpty)
    }

    @Test("finishing an unknown id is a no-op")
    func finishUnknownIsNoOp() {
        var registry = WorkflowRunRegistry()
        registry.register(run("Google"))
        registry.finish(UUID())
        #expect(registry.count == 1)
    }

    // MARK: - A run freezes its steps, scope and context at launch

    @Test("a launched run freezes its steps, scope and context")
    func launchedRunFreezesInputs() {
        let launched = run("Google", docIds: ["a", "b"], context: "diary")
        #expect(launched.scope == .documents(ids: ["a", "b"]))
        #expect(launched.userContext == "diary")
        #expect(launched.steps.map(\.name) == ["Google"])
    }

    // MARK: - Title derivation

    @Test("a multi-step run names its head plus a count")
    func multiStepRunTitle() {
        let launched = ActiveWorkflowRun(
            steps: [
                step(id: "wf-1", name: "Transcribe"),
                step(id: "wf-2", name: "Clean up"),
                step(id: "wf-3", name: "Catalogue")
            ],
            scope: .documents(ids: ["doc-1"]),
            userContext: ""
        )
        #expect(launched.title == "Transcribe +2")
    }

    @Test("a single-step run is named for that step alone")
    func singleStepRunTitle() {
        #expect(run("Transcribe").title == "Transcribe")
    }
}
