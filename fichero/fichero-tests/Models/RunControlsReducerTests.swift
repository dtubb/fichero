@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

// #4321: run controls were fire-and-forget — no state applied, no
// (re)subscribe, divergent button sets between Monitor and Detail, and
// cancelled rendered as Failed. These tests pin the pure pieces of the
// transactional path: the status bridges over the generated RunStatus enum,
// the control-response reducer, the subscribe policy, and the one action
// vocabulary both surfaces render.
@MainActor
@Suite("Run controls reducer & status bridges (#4321)")
struct RunControlsReducerTests {

    private func thread(
        _ status: ExecutionStatus,
        threadId: String = "thread-1",
        error: String? = nil
    ) -> ExecutionThread {
        ExecutionThread(
            threadId: threadId,
            workflowId: "wf-1",
            workflowName: "Transcribe",
            status: status,
            checkpointId: nil,
            error: error
        )
    }

    // MARK: - Generated RunStatus → ExecutionStatus (typed end-to-end)

    @Test("every generated RunStatus case maps onto the app ExecutionStatus")
    func generatedRunStatusBridge() {
        #expect(WorkflowExecutionService.mapStatus(Components.Schemas.RunStatus.accepted) == .running)
        #expect(WorkflowExecutionService.mapStatus(Components.Schemas.RunStatus.running) == .running)
        #expect(WorkflowExecutionService.mapStatus(Components.Schemas.RunStatus.paused) == .paused)
        #expect(WorkflowExecutionService.mapStatus(Components.Schemas.RunStatus.completed) == .completed)
        #expect(WorkflowExecutionService.mapStatus(Components.Schemas.RunStatus.failed) == .failed)
        #expect(WorkflowExecutionService.mapStatus(Components.Schemas.RunStatus.cancelled) == .cancelled)
        #expect(WorkflowExecutionService.mapStatus(Components.Schemas.RunStatus.deleted) == .deleted)
    }

    // MARK: - ExecutionStatus → WorkflowStatus

    @Test("cancelled/stopped/deleted map to .cancelled — never .failed")
    func executionStatusBridge() {
        #expect(WorkflowExecution.workflowStatus(from: .running) == .running)
        #expect(WorkflowExecution.workflowStatus(from: .paused) == .paused)
        #expect(WorkflowExecution.workflowStatus(from: .completed) == .completed)
        #expect(WorkflowExecution.workflowStatus(from: .failed) == .failed)
        #expect(WorkflowExecution.workflowStatus(from: .error) == .failed)
        #expect(WorkflowExecution.workflowStatus(from: .cancelled) == .cancelled)
        #expect(WorkflowExecution.workflowStatus(from: .stopped) == .cancelled)
        #expect(WorkflowExecution.workflowStatus(from: .deleted) == .cancelled)
    }

    @Test("raw backend strings keep cancelled distinct from failed")
    func rawStatusBridge() {
        #expect(WorkflowExecution.workflowStatus(fromRaw: "cancelled") == .cancelled)
        #expect(WorkflowExecution.workflowStatus(fromRaw: "stop_requested") == .cancelled)
        #expect(WorkflowExecution.workflowStatus(fromRaw: "failed") == .failed)
        #expect(WorkflowExecution.workflowStatus(fromRaw: "paused") == .paused)
    }

    // MARK: - Control-response reducer

    @Test("resume response patches the existing entry in place")
    func reducedPatchesExistingEntry() {
        var existing = WorkflowExecution(
            id: "wf-1",
            name: "Transcribe",
            threadId: "thread-1",
            startTime: Date(timeIntervalSince1970: 100),
            status: .paused,
            nodeStates: ["node-1": NodeExecutionState(nodeId: "node-1", displayName: "OCR", status: .completed)],
            documentProgress: [:],
            currentFilePath: nil,
            currentNodeId: nil,
            currentNodeName: nil,
            isRunning: false,
            workflowError: nil
        )
        existing.processedFiles = 3

        let reduced = WorkflowExecutionStore.reduced(existing, thread: thread(.running))

        #expect(reduced.status == .running)
        #expect(reduced.isRunning)
        #expect(reduced.startTime == Date(timeIntervalSince1970: 100), "reduced state must not be fabricated anew")
        #expect(reduced.nodeStates["node-1"]?.status == .completed, "node/file progress survives the control action")
        #expect(reduced.processedFiles == 3)
    }

    @Test("an untracked thread (CLI-launched) seeds a minimal entry")
    func reducedSeedsUntrackedThread() {
        let reduced = WorkflowExecutionStore.reduced(nil, thread: thread(.paused))

        #expect(reduced.threadId == "thread-1")
        #expect(reduced.id == "wf-1")
        #expect(reduced.status == .paused)
        #expect(reduced.isRunning == false)
    }

    @Test("a cancel response lands as cancelled with the server's error")
    func reducedCancelledCarriesError() {
        let reduced = WorkflowExecutionStore.reduced(
            nil,
            thread: thread(.cancelled, error: "Cancelled by user")
        )
        #expect(reduced.status == .cancelled)
        #expect(reduced.workflowError == "Cancelled by user")
    }

    // MARK: - Subscribe policy

    @Test("non-terminal runs subscribe — paused included — terminal ones do not")
    func subscribePolicy() {
        #expect(WorkflowExecutionStore.shouldSubscribe(status: .running))
        #expect(WorkflowExecutionStore.shouldSubscribe(status: .paused), "paused runs were never subscribed, so Resume could never visibly work")
        #expect(!WorkflowExecutionStore.shouldSubscribe(status: .completed))
        #expect(!WorkflowExecutionStore.shouldSubscribe(status: .failed))
        #expect(!WorkflowExecutionStore.shouldSubscribe(status: .cancelled))
        #expect(!WorkflowExecutionStore.shouldSubscribe(status: .idle))
    }

    // MARK: - One action vocabulary for both surfaces

    @Test("RunControls offers the same buttons per status everywhere")
    func runControlActions() {
        #expect(RunControls.actions(for: .running) == [.pause, .stop])
        #expect(RunControls.actions(for: .paused) == [.resume, .stop])
        #expect(RunControls.actions(for: .completed) == [.delete])
        #expect(RunControls.actions(for: .failed) == [.delete])
        #expect(RunControls.actions(for: .cancelled) == [.delete])
        #expect(RunControls.actions(for: .idle) == [.delete])
    }
}
