//
//  WorkflowBarChainPersistenceTests.swift
//  FicheroTests
//
//  The workflow bar's staged chain rides the engine's ChainService
//  (2026-08-30, workflow-bar review ruling): staged steps persist as engine
//  chain steps and come back as the same rail, per-step model pins ride the
//  new provider_override/model_override fields, engine step statuses map onto
//  chip states, and the execute-steps call feature-detects an older engine
//  (404 → the client loop takes over, never a broken bar).
//

@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

struct WorkflowBarChainPersistenceTests {

    private func workflowItem(id: String, name: String) -> WorkflowSidebarItem {
        WorkflowSidebarItem(id: id, name: name)
    }

    private func workflowStep(
        id: String, name: String, provider: String? = nil, model: String? = nil
    ) -> StagedWorkflowStep {
        StagedWorkflowStep(
            kind: .workflow(workflowItem(id: id, name: name)),
            providerOverride: provider,
            modelOverride: model
        )
    }

    // MARK: - Staged → engine steps

    @Test("workflow steps persist with their own model pins, in rail order")
    func workflowStepsPersist() {
        let staged = [
            workflowStep(id: "wf-1", name: "Transcribe",
                         provider: "anthropic", model: "claude-opus-4-7"),
            workflowStep(id: "wf-2", name: "Entities")
        ]
        let steps = WorkflowBarChainPersistence.chainSteps(from: staged)

        #expect(steps.map(\.workflowId) == ["wf-1", "wf-2"])
        #expect(steps.map(\.name) == ["Transcribe", "Entities"])
        // The step's engine id IS the chip's UUID — that is what lets the
        // accept response and status polls address chips directly.
        #expect(steps.map(\.id) == staged.map { $0.id.uuidString })
        // Each step carries its OWN pin; an unpinned step stays nil so the
        // workflow resolves its own alias.
        #expect(steps[0].providerOverride == "anthropic")
        #expect(steps[0].modelOverride == "claude-opus-4-7")
        #expect(steps[1].providerOverride == nil)
        #expect(steps[1].modelOverride == nil)
    }

    @Test("a tool step rides its identity in static_inputs and takes a resolved workflow id")
    func toolStepPersists() {
        let tool = StagedWorkflowStep(
            kind: .tool(name: "summarize", displayName: "Summarize",
                        icon: "text.append", usesLLM: true)
        )
        let unresolved = WorkflowBarChainPersistence.chainSteps(from: [tool])
        // Not yet realised: no workflow id to claim.
        #expect(unresolved[0].workflowId.isEmpty)
        #expect(unresolved[0].staticInputs["staged_tool_name"] == .string("summarize"))

        let resolved = WorkflowBarChainPersistence.chainSteps(
            from: [tool], resolvedWorkflowIds: [tool.id: "wf-tool-1"]
        )
        #expect(resolved[0].workflowId == "wf-tool-1")
        // The marker survives resolution, so a later restore still shows a
        // tool chip rather than a mystery one-step workflow.
        #expect(resolved[0].staticInputs["staged_kind"] == .string("tool"))
    }

    // MARK: - Engine chain → staged rail

    @Test("a persisted chain restores kinds, order and pins")
    func restoreRoundTrip() {
        let tool = StagedWorkflowStep(
            kind: .tool(name: "summarize", displayName: "Summarize",
                        icon: "text.append", usesLLM: true)
        )
        let staged = [
            workflowStep(id: "wf-1", name: "Transcribe",
                         provider: "apple", model: "afm-on-device"),
            tool
        ]
        let chain = WorkflowChain(
            name: WorkflowBarChainPersistence.chainName,
            steps: WorkflowBarChainPersistence.chainSteps(
                from: staged, resolvedWorkflowIds: [tool.id: "wf-tool-1"]
            )
        )
        let restored = WorkflowBarChainPersistence.stagedSteps(
            from: chain,
            workflows: [workflowItem(id: "wf-1", name: "Transcribe")]
        )

        #expect(restored.count == 2)
        #expect(restored[0].workflow?.id == "wf-1")
        #expect(restored[0].providerOverride == "apple")
        #expect(restored[0].modelOverride == "afm-on-device")
        guard case .tool(let name, let display, let icon, let usesLLM) = restored[1].kind else {
            Issue.record("expected the second step to restore as a tool")
            return
        }
        #expect(name == "summarize")
        #expect(display == "Summarize")
        #expect(icon == "text.append")
        #expect(usesLLM)
    }

    @Test("a step whose workflow was deleted is dropped, not resurrected as an unrunnable chip")
    func deletedWorkflowDropped() {
        let chain = WorkflowChain(
            name: WorkflowBarChainPersistence.chainName,
            steps: [
                ChainStep(workflowId: "wf-gone", name: "Gone"),
                ChainStep(workflowId: "wf-here", name: "Here")
            ]
        )
        let restored = WorkflowBarChainPersistence.stagedSteps(
            from: chain,
            workflows: [workflowItem(id: "wf-here", name: "Here")]
        )
        #expect(restored.count == 1)
        #expect(restored[0].workflow?.id == "wf-here")
    }

    // MARK: - Engine statuses → chip states

    @Test("engine step statuses map onto chip states; skipped reads as un-run")
    func stepStateMapping() {
        // `skipped` is the engine's stop-on-failure leaving later steps
        // un-run — the rail's language for that has always been a pending
        // chip showing exactly where the chain stopped.
        #expect(WorkflowBarChainPersistence.stepState(fromEngineStatus: .pending) == .pending)
        #expect(WorkflowBarChainPersistence.stepState(fromEngineStatus: .skipped) == .pending)
        #expect(WorkflowBarChainPersistence.stepState(fromEngineStatus: .running) == .running)
        #expect(WorkflowBarChainPersistence.stepState(fromEngineStatus: .completed) == .succeeded)
        #expect(WorkflowBarChainPersistence.stepState(fromEngineStatus: .failed) == .failed)
        #expect(WorkflowBarChainPersistence.stepState(fromEngineStatus: .cancelled) == .failed)
    }

    @Test("terminal statuses end the poll; running/pending keep it alive")
    func terminalStatuses() {
        #expect(WorkflowBarChainPersistence.isTerminal("completed"))
        #expect(WorkflowBarChainPersistence.isTerminal("failed"))
        #expect(WorkflowBarChainPersistence.isTerminal("cancelled"))
        #expect(!WorkflowBarChainPersistence.isTerminal("pending"))
        #expect(!WorkflowBarChainPersistence.isTerminal("running"))
    }

    // MARK: - Persistence identity

    @Test("structure key tracks steps, order and pins — never run-state churn")
    func structureKeyIdentity() {
        var first = workflowStep(id: "wf-1", name: "A")
        var second = workflowStep(id: "wf-2", name: "B")
        let key = WorkflowBarChainPersistence.structureKey(for: [first, second])

        // Chip state and thread id churn during a run must NOT re-persist.
        first.state = .running
        second.threadId = "thread-abc"
        #expect(WorkflowBarChainPersistence.structureKey(for: [first, second]) == key)

        // Reorder and re-pin ARE structural.
        #expect(WorkflowBarChainPersistence.structureKey(for: [second, first]) != key)
        second.modelOverride = "claude-opus-4-7"
        #expect(WorkflowBarChainPersistence.structureKey(for: [first, second]) != key)
    }
}
