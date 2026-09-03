import SwiftUI

// The COMPARE fan-out's host side (Daniel, 2026-08-30, reading-markup-coding
// design item 6): run the ONE staged step once per configured model. Kept in
// its own file for the same type-checker-budget reason as the bar hosting.
extension ContentView {

    /// Run the staged step once per model, sequentially, all stamped with the
    /// same fresh `compare_group` id.
    ///
    /// Sequential like the chain, but for a different reason: the runs do not
    /// feed each other, they just must not stampede the engine (and each is a
    /// paid call the user confirmed one press at a time is easiest to stop).
    /// Unlike a chain, a FAILED run does not stop the rest — a comparison
    /// wants every model's answer, and model three failing says nothing about
    /// model four.
    @MainActor
    func runModelCompare(runs: [WorkflowCompareRun], groupId: String) async {
        guard !runs.isEmpty, !isRunningStagedChain,
              stagedWorkflowChain.count == 1,
              let step = stagedWorkflowChain.first
        else { return }
        isRunningStagedChain = true
        defer {
            isRunningStagedChain = false
            runningStagedStepIndex = nil
        }

        // Freeze the SCOPE once, exactly as the chain does — a paid fan-out
        // must not follow a selection that wanders mid-run.
        let scope = workflowBarRunScope
        guard let targets = await frozenChainTargets(for: scope) else { return }
        let hints = Self.artifactHints(for: scope)
        lastChainRunTargets = targets

        chromeUX.compareRunProgress = runs.map {
            WorkflowCompareRunProgress(
                id: $0.model,
                label: ModelChipToolbarItem.shorten($0.model)
            )
        }

        func update(
            _ model: String,
            _ state: StagedStepState,
            reason: String? = nil,
            threadId: String? = nil
        ) {
            guard let index = chromeUX.compareRunProgress
                .firstIndex(where: { $0.id == model }) else { return }
            chromeUX.compareRunProgress[index].state = state
            // A re-run of the same fan-out must not leave last time's reason
            // hanging off a capsule that has since gone green: a non-failed
            // state clears it.
            chromeUX.compareRunProgress[index].failureReason =
                state == .failed ? reason : nil
            if let threadId { chromeUX.compareRunProgress[index].threadId = threadId }
        }

        // One resolution for the whole fan-out — every run IS the same step,
        // only the model pin differs.
        guard let workflowId = await resolveWorkflowId(for: step) else {
            // One reason, and it is the same for every capsule here — the step
            // itself could not be realised, so no model was ever asked.
            let reason = "This step could not be prepared to run, so no model was called."
            for run in runs { update(run.model, .failed, reason: reason) }
            setStagedStepState(step.id, .failed)
            return
        }

        setStagedStepState(step.id, .running)
        var anySucceeded = false
        for run in runs {
            update(run.model, .running)
            let threadId = await awaitWorkflowExecution(
                workflowId: workflowId,
                workflowName: "\(step.name) (\(ModelChipToolbarItem.shorten(run.model)))",
                docIds: targets,
                providerOverride: run.provider,
                modelOverride: run.model,
                artifactTypeHint: hints.type,
                artifactStepNameHint: hints.stepName,
                compareGroup: groupId,
                // Stamped the moment the server accepts, so a capsule can name
                // its own run even while it is still going.
                onThreadId: { accepted in update(run.model, .running, threadId: accepted) }
            )
            let execution = executionObserver.getExecution(threadId: threadId)
            let succeeded = execution?.status == .completed
            // The engine's own words, kept per model (Daniel, 2026-09-02):
            // "Vision LLM returned empty response … after retry" belongs to
            // the ONE model that returned nothing, not to the fan-out. Three
            // models succeeding and one failing is a RESULT of a comparison,
            // not an error in it, which is exactly what a global alert could
            // not express.
            update(
                run.model,
                succeeded ? .succeeded : .failed,
                reason: succeeded ? nil : execution?.workflowError,
                threadId: threadId
            )
            anySucceeded = anySucceeded || succeeded
        }
        // The chip states whether the COMPARISON produced anything to look
        // at; the per-model capsules carry the fine grain.
        setStagedStepState(step.id, anySucceeded ? .succeeded : .failed)

        // SEAM(compare-reader): the sibling lane adds the reader's compare
        // representation (columns per model, labeled diff) keyed on the
        // `compare_group` these runs carry — completion surfaces there and in
        // the existing execution observer UI; nothing more to open from here
        // yet.
    }

    /// Price the compare fan-out: the ONE staged step, once per configured
    /// model, summed. nil when the fan-out is unavailable or nothing can be
    /// priced — the confirmation then says so rather than reading as free.
    @MainActor
    func refreshCompareCostCeiling() async {
        guard let runs = WorkflowComparePlanner.fanOut(
            staged: stagedWorkflowChain, choices: workflowBarModelChoices
        ), let workflowId = stagedWorkflowChain.first?.workflow?.id else {
            chromeUX.stagedCompareCostCeiling = nil
            return
        }
        var total = 0.0
        var priced = false
        for run in runs {
            if let cost = await workflowStore.estimateStepCost(
                workflowId: workflowId,
                fileCount: workflowBarTargetCount,
                provider: run.provider,
                model: run.model
            ) {
                total += cost
                priced = true
            }
        }
        chromeUX.stagedCompareCostCeiling = priced ? total : nil
    }

    /// An artifact scope carries the type/step hint every run must honour.
    private static func artifactHints(
        for scope: WorkflowBarPolicy.RunScope
    ) -> (type: String?, stepName: String?) {
        if case .artifact(_, _, _, _, let artifactType, let stepName) = scope {
            return (artifactType, stepName)
        }
        return (nil, nil)
    }

    /// Write one staged chip's state by ID — chips stay removable while runs
    /// are live, so a captured index could drift onto a different step.
    @MainActor
    private func setStagedStepState(_ stepId: UUID, _ state: StagedStepState) {
        if let index = stagedWorkflowChain.firstIndex(where: { $0.id == stepId }) {
            stagedWorkflowChain[index].state = state
        }
    }
}
