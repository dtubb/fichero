import OSLog
import SwiftUI

private let engineChainLogger = Logger(
    subsystem: "app.fichero.fichero",
    category: "WorkflowBarChain"
)

// The staged chain rides the engine's ChainService (Daniel, 2026-08-30,
// workflow-bar review ruling): persistence so the rail survives window
// close/reopen and reads the same cross-window, and execution so the ENGINE
// owns ordering, per-step model overrides and stop-on-failure. The client
// loop in ContentView+WorkflowBar stays as the fallback for an engine
// without the execute-steps route — feature-detected, never assumed.
extension ContentView {

    /// The per-library chain service, shared by every window on the library.
    var workflowBarChainService: ChainService? {
        windowState.library?.chainService
    }

    /// One chip mutation by step ID — indexes drift while chips stay
    /// draggable during a run (review, 2026-08-29).
    @MainActor
    func updateStagedStep(_ stepId: UUID, _ mutate: (inout StagedWorkflowStep) -> Void) {
        if let liveIndex = stagedWorkflowChain.firstIndex(where: { $0.id == stepId }) {
            mutate(&stagedWorkflowChain[liveIndex])
        }
    }

    // MARK: - Persistence

    /// Write the staged rail to the engine's "Workflow Bar" chain.
    ///
    /// Create-on-first-stage, update after; the id is remembered so staging
    /// edits are one PUT each. Persistence failing must never block staging —
    /// the rail keeps working locally and the next edit retries.
    @MainActor
    @discardableResult
    func persistStagedChain(
        resolvedWorkflowIds: [UUID: String] = [:],
        stampResolvedModels: Bool = false
    ) async -> String? {
        guard let service = workflowBarChainService else { return nil }
        // Only a RUN stamps the resolved model (2026-09-01). Staging persists
        // the rail as the user assembled it, so a chain restored next week
        // still follows whatever Settings say then.
        var overrides: [UUID: WorkflowBarModelChoice] = [:]
        if stampResolvedModels {
            for step in stagedWorkflowChain {
                // The SAME resolution the sentence shows and the client
                // fallback loop sends — pin, tier correction, or the picker's
                // choice for a single staged preset (Daniel, 2026-09-04: "the
                // model chosen is not the model used"). This path stamped the
                // implicit tier correction ALONE, which is tool-steps-only:
                // a staged preset therefore rode the engine chain carrying no
                // model at all, and the engine fell back to the preset's own
                // node models or the stored defaults. That is the
                // "routing to Apple Intelligence" Daniel is seeing, and the
                // Paleographer Review that ran on gemini under an opus chip.
                let resolved = workflowBarRunOverrides(
                    for: step, stagedCount: stagedWorkflowChain.count
                )
                guard let model = resolved.model, !model.isEmpty else { continue }
                overrides[step.id] = WorkflowBarModelChoice(
                    label: ModelChipToolbarItem.shorten(model),
                    provider: resolved.provider ?? "",
                    model: model
                )
            }
        }
        let steps = WorkflowBarChainPersistence.chainSteps(
            from: stagedWorkflowChain,
            resolvedWorkflowIds: resolvedWorkflowIds,
            modelOverrides: overrides
        )
        do {
            if let chain = try await findWorkflowBarChain(service) {
                var updated = chain
                updated.steps = steps
                _ = try await service.updateChain(updated)
                workflowBarChainId = chain.id
                return chain.id
            }
            let created = try await service.createChain(
                name: WorkflowBarChainPersistence.chainName,
                description: "The chain staged in the workflow bar.",
                steps: steps
            )
            workflowBarChainId = created.id
            return created.id
        } catch {
            engineChainLogger.warning(
                "Staged-chain persist failed: \(error.localizedDescription)"
            )
            return nil
        }
    }

    @MainActor
    private func findWorkflowBarChain(_ service: ChainService) async throws -> WorkflowChain? {
        if let chainId = workflowBarChainId {
            if let chain = try? await service.getChain(chainId) { return chain }
            // The remembered chain vanished (engine restart — the store is
            // in-memory; or deleted in the sidebar). Fall through to by-name.
            workflowBarChainId = nil
        }
        return try await service.listChains()
            .first { $0.name == WorkflowBarChainPersistence.chainName }
    }

    /// One structure-change tick from the bar: restore first (an empty bar,
    /// once per window), then persist what is staged. The 400ms sleep is the
    /// debounce — a reorder-drag changes the structure key per hop and
    /// `.task(id:)` cancels every superseded hop, so only the settled rail
    /// is written.
    @MainActor
    func syncStagedChainWithEngine() async {
        await restoreStagedChainIfNeeded()
        if !stagedWorkflowChain.isEmpty || workflowBarChainId != nil {
            try? await Task.sleep(for: .milliseconds(400))
            guard !Task.isCancelled else { return }
            await persistStagedChain()
        }
    }

    /// Load the persisted rail into an EMPTY bar, once per window lifetime.
    ///
    /// Waits (bounded) for the workflow list, because restoring against an
    /// unloaded list would drop every workflow step as "deleted".
    @MainActor
    func restoreStagedChainIfNeeded() async {
        guard stagedWorkflowChain.isEmpty,
              !workflowBarChainRestoreAttempted,
              let service = workflowBarChainService else { return }
        for attempt in 0..<6 where workflowStore.workflows.isEmpty {
            try? await Task.sleep(for: .seconds(Double(attempt + 1)))
        }
        workflowBarChainRestoreAttempted = true
        guard let chain = try? await service.listChains()
            .first(where: { $0.name == WorkflowBarChainPersistence.chainName })
        else { return }
        workflowBarChainId = chain.id
        let steps = WorkflowBarChainPersistence.stagedSteps(
            from: chain, workflows: workflowStore.workflows
        )
        // Re-check emptiness: the user may have staged while we waited.
        if stagedWorkflowChain.isEmpty, !steps.isEmpty {
            stagedWorkflowChain = steps
            engineChainLogger.info("Restored \(steps.count) staged chain steps")
        }
    }

    // MARK: - Engine execution

    /// Run the staged chain: engine-side when this engine can, the local
    /// loop when it cannot. The behavior contract (chip states, frozen
    /// scope, stop-on-failure, repeatable chain) is identical either way.
    @MainActor
    func runStagedChain() async {
        guard !stagedWorkflowChain.isEmpty, !isRunningStagedChain else { return }
        if await runStagedChainViaEngine() { return }
        await runStagedChainClientSide()
    }

    /// Returns false ONLY when the engine lacks step execution and the
    /// client loop should take over; true means the run was handled here,
    /// whatever its outcome.
    @MainActor
    func runStagedChainViaEngine() async -> Bool {
        guard let service = workflowBarChainService else { return false }

        // Realise every step FIRST (tool steps become one-step workflows,
        // exactly as the client loop does at each step). An unrealisable
        // step fails its chip and stops before any money is spent.
        var resolved: [UUID: String] = [:]
        for step in stagedWorkflowChain {
            guard let workflowId = await resolveWorkflowId(for: step) else {
                updateStagedStep(step.id) { $0.state = .failed }
                return true
            }
            resolved[step.id] = workflowId
        }

        guard let chainId = await persistStagedChain(
            resolvedWorkflowIds: resolved, stampResolvedModels: true
        ) else { return false }
        guard let launch = await frozenEngineChainLaunch() else { return true }
        lastChainRunTargets = launch.targets

        isRunningStagedChain = true
        chromeUX.compareRunProgress = []
        defer {
            isRunningStagedChain = false
            runningStagedStepIndex = nil
        }
        for index in stagedWorkflowChain.indices {
            stagedWorkflowChain[index].state = .pending
        }

        do {
            let execution = try await service.executeChainSteps(
                chainId: chainId, inputs: launch.inputs
            )
            // Stamp thread ids the moment the engine assigns them, so a
            // running chip opens its live trace exactly as before.
            for stepInfo in execution.steps {
                if let stepUUID = UUID(uuidString: stepInfo.stepId) {
                    updateStagedStep(stepUUID) { $0.threadId = stepInfo.threadId }
                }
            }
            await followEngineChainExecution(execution, service: service)
            // Un-stamp: the resolved models were this RUN's, not pins the
            // user made. Left behind, a chain restored next week would come
            // back pinned to models Settings has since moved on from.
            await persistStagedChain(resolvedWorkflowIds: resolved)
            return true
        } catch ChainServiceError.stepExecutionUnavailable {
            // Older engine: no execute-steps route. The client loop still
            // knows how to run this chain — feature-detect, don't break.
            engineChainLogger.info("Engine lacks chain step execution; falling back")
            return false
        } catch {
            importError = "Chain failed to start: \(error.localizedDescription)"
            engineChainLogger.error("executeChainSteps failed: \(error.localizedDescription)")
            return true
        }
    }

    private struct EngineChainLaunch {
        let targets: [String]
        let inputs: [String: AnyCodableValue]
    }

    /// Freeze the SCOPE once — the same promise the client loop makes: the
    /// run acts on what was selected at press time, wherever the selection
    /// wanders during it. The scope's artifact hints ride the run inputs.
    @MainActor
    private func frozenEngineChainLaunch() async -> EngineChainLaunch? {
        let scope = workflowBarRunScope
        guard let targets = await frozenChainTargets(for: scope) else { return nil }
        var artifactTypeHint: String?
        var artifactStepNameHint: String?
        if case .artifact(_, _, _, _, let artifactType, let stepName) = scope {
            artifactTypeHint = artifactType
            artifactStepNameHint = stepName
        }
        let inputs = WorkflowRunInputs.build(
            docIds: targets,
            userContext: workflowUserContext,
            artifactTypeHint: artifactTypeHint,
            artifactStepNameHint: artifactStepNameHint,
            compareGroup: nil
        )
        return EngineChainLaunch(
            targets: targets, inputs: Self.codableRunInputs(inputs)
        )
    }

    /// Track the engine-owned run onto the chips by polling the execution
    /// status — the engine is the one source of per-step truth now.
    @MainActor
    private func followEngineChainExecution(
        _ execution: ChainStepsExecution,
        service: ChainService
    ) async {
        var started: Set<String> = []
        var ended: Set<String> = []
        // A chain of paid model calls can legitimately run a long time; the
        // deadline only guards against polling a wedged engine forever.
        let deadline = Date().addingTimeInterval(4 * 60 * 60)
        while Date() < deadline {
            guard let status = try? await service.getExecutionStatus(execution.executionId)
            else {
                try? await Task.sleep(for: .seconds(2))
                continue
            }
            applyEngineStepResults(status, threads: execution.steps,
                                   started: &started, ended: &ended)
            if WorkflowBarChainPersistence.isTerminal(status.status) { break }
            try? await Task.sleep(for: .seconds(1))
        }
        // A completed step may have written per-page content; show it fresh,
        // as the SSE path does at its terminal boundary (#1445).
        await documentStore.refreshDocumentsByIds(lastChainRunTargets)
        if !executionObserver.hasRunningExecution {
            documentStore.clearResidualProcessing()
        }
    }

    /// One poll tick onto the rail: chip states, the running index, and the
    /// Activity rows for steps as the engine starts and settles them.
    @MainActor
    private func applyEngineStepResults(
        _ status: ChainExecutionStatusResponse,
        threads: [ChainStepThread],
        started: inout Set<String>,
        ended: inout Set<String>
    ) {
        runningStagedStepIndex = nil
        for result in status.stepResults {
            guard let stepUUID = UUID(uuidString: result.stepId) else { continue }
            updateStagedStep(stepUUID) {
                $0.state = WorkflowBarChainPersistence.stepState(fromEngineStatus: result.status)
            }
            if result.status == .running {
                runningStagedStepIndex = stagedWorkflowChain
                    .firstIndex { $0.id == stepUUID }
            }
            guard let thread = threads.first(where: { $0.stepId == result.stepId })
            else { continue }
            let stepName = stagedWorkflowChain
                .first { $0.id == stepUUID }?.name ?? thread.name
            switch result.status {
            case .running:
                if started.insert(thread.threadId).inserted {
                    executionObserver.startExecution(
                        workflowId: thread.workflowId,
                        name: stepName,
                        threadId: thread.threadId
                    )
                }
            case .completed, .failed, .cancelled:
                if started.contains(thread.threadId),
                   ended.insert(thread.threadId).inserted {
                    executionObserver.endExecution(
                        threadId: thread.threadId,
                        status: result.status == .completed ? .completed
                            : result.status == .cancelled ? .cancelled : .failed
                    )
                }
            case .pending, .skipped:
                break
            }
        }
    }

    /// `WorkflowRunInputs.build` output (doc-id arrays and strings, by
    /// construction) as the typed dictionary the chain API takes. Anything
    /// unencodable is dropped with a log rather than crashing a run.
    static func codableRunInputs(_ inputs: [String: Any]) -> [String: AnyCodableValue] {
        guard JSONSerialization.isValidJSONObject(inputs),
              let data = try? JSONSerialization.data(withJSONObject: inputs),
              let decoded = try? JSONDecoder().decode([String: AnyCodableValue].self, from: data)
        else {
            engineChainLogger.error("Run inputs were not JSON-encodable; sending empty")
            return [:]
        }
        return decoded
    }
}
