import OSLog
import SwiftUI

private let barLogger = Logger(
    subsystem: "app.fichero.fichero",
    category: "WorkflowBar"
)

// Hosting for the capability bar (2026-08-28). Kept in its own file, and as
// ONE small property, because the layout files it attaches to already carry
// chained-modifier lists split three ways to stay inside the Swift
// type-checker's budget — see ContentView+RootLayout.
extension ContentView {

    /// The bar, or nothing when it is switched off. Attached as a top safe-area
    /// inset on the detail column so it spans the content and NOT the sidebar
    /// or inspector: it acts on the content selection, and a window-wide row
    /// would claim a scope it does not have.
    /// The window-level annotation bar (Daniel, 2026-08-30): same detail-
    /// column scope as the workflow bar, directly under the toolbar.
    @ViewBuilder
    var annotationBarInset: some View {
        if showAnnotationBar {
            AnnotationBar(showsLabels: showWorkflowBarLabels)
                .background { ToolbarTextModeSync(showsLabels: $showWorkflowBarLabels) }
        }
    }

    @ViewBuilder
    var workflowBarInset: some View {
        if showWorkflowBar {
            WorkflowBar(
                workflows: workflowStore.workflows,
                target: workflowBarTarget,
                folders: workflowStore.folderPresentation,
                modelChoices: workflowBarModelChoices,
                showsLabels: showWorkflowBarLabels,
                staged: $stagedWorkflowChain,
                onRunChain: { Task { await runStagedChain() } },
                isRunning: isRunningStagedChain,
                runningStepIndex: runningStagedStepIndex,
                onOpenStep: { openStagedStepResult($0) },
                costCeiling: stagedChainCostCeiling,
                tools: Array(workflowStore.toolRegistry.values),
                // ⓘ goes to the node editor — the existing .workflow content
                // mode, not a new surface: graph, steps, prompt preview.
                onInspectWorkflow: { viewMode = .workflow($0) },
                targetDetail: workflowBarTargetDetail,
                userContext: $workflowUserContext,
                scopeOptions: workflowBarScopeOptions,
                onSelectScope: { selectWorkflowScope($0) },
                onRunCompare: { runs, groupId in
                    Task { await runModelCompare(runs: runs, groupId: groupId) }
                },
                compareProgress: chromeUX.compareRunProgress,
                compareCostCeiling: chromeUX.stagedCompareCostCeiling,
                // The sentence names the model a run would REALLY use
                // (Daniel, 2026-08-31: "rather than say default model,
                // actually use the model name").
                defaultModelName: selectionPrefersVisionModel
                    ? cachedAIDefaults.visionMediumModel
                    : cachedAIDefaults.mediumModel,
                prefersVisionModel: selectionPrefersVisionModel
            )
            // On BOTH bars: labels follow the toolbar when only one is shown.
            .background { ToolbarTextModeSync(showsLabels: $showWorkflowBarLabels) }
            .task(id: chainCostKey) { await refreshChainCostCeiling() }
            // Persist/restore keyed on the chain's STRUCTURE — steps, order,
            // pins — never run-state churn. See ContentView+WorkflowChainEngine.
            .task(id: WorkflowBarChainPersistence.structureKey(for: stagedWorkflowChain)) {
                await syncStagedChainWithEngine()
            }
            .task {
                // Refresh when the bar appears rather than at launch: the menu
                // is only consulted here, and a stale tier would offer a model
                // the user has since changed.
                //
                // Bounded retry, not one `try?` (review, 2026-08-29): the
                // first attempt fires when a scene restores with the bar
                // already on, which loses a race with the engine coming up —
                // the model chip already learned this the hard way, and one
                // lost race here left the per-step pin menu EMPTY forever.
                for attempt in 0..<6 {
                    if let loaded = try? await appState.fetchAIDefaults() {
                        cachedAIDefaults = loaded
                        return
                    }
                    try? await Task.sleep(for: .seconds(Double(attempt + 1)))
                }
            }
        }
    }

    /// FALLBACK: run the staged chain client-side, one step after another on
    /// the same selection.
    ///
    /// The engine now owns chain execution (`runStagedChainViaEngine`,
    /// 2026-08-30) — order, per-step overrides, stop-on-failure. This loop
    /// remains for an older engine without the execute-steps route, feature-
    /// detected by `runStagedChain` in ContentView+WorkflowChainEngine.
    ///
    /// Sequential, not fire-and-forget: step two should read what step one
    /// wrote (transcribe then clean up then catalogue), so each awaits the
    /// one before it. The chain is NOT cleared on completion — a run you can
    /// repeat on the next folder is the point of having assembled it.
    @MainActor
    func runStagedChainClientSide() async {
        guard !stagedWorkflowChain.isEmpty, !isRunningStagedChain else { return }
        isRunningStagedChain = true
        // A plain run supersedes whatever the last compare showed — stale
        // per-model capsules under a fresh chain run would claim runs this
        // press never made.
        chromeUX.compareRunProgress = []
        defer {
            isRunningStagedChain = false
            runningStagedStepIndex = nil
        }

        // Freeze the SCOPE once. Selection can move while a long chain runs,
        // and step four landing on documents the user picked mid-run is the
        // kind of surprise a paid job must never spring. The scope, not just
        // ids: an artifact scope also carries the type/step hint every step
        // of this run must keep honoring.
        let scope = workflowBarRunScope
        guard let targets = await frozenChainTargets(for: scope) else { return }
        var artifactTypeHint: String?
        var artifactStepNameHint: String?
        if case .artifact(_, _, _, _, let artifactType, let stepName) = scope {
            artifactTypeHint = artifactType
            artifactStepNameHint = stepName
        }
        // What "see what it produced" opens later, however the live selection
        // wanders during the run.
        lastChainRunTargets = targets

        // Every step starts pending again, so a re-run does not show last
        // time's greens while this time's work is still ahead.
        for index in stagedWorkflowChain.indices {
            stagedWorkflowChain[index].state = .pending
        }

        // All chip-state writes go through the step's ID, not its index
        // (review, 2026-08-29): chips stay removable and draggable while a
        // chain runs, so a captured index can drift onto a DIFFERENT step —
        // painting the wrong chip green, or writing past the end.
        func update(_ stepId: UUID, _ mutate: (inout StagedWorkflowStep) -> Void) {
            if let liveIndex = stagedWorkflowChain.firstIndex(where: { $0.id == stepId }) {
                mutate(&stagedWorkflowChain[liveIndex])
            }
        }

        for step in stagedWorkflowChain {
            runningStagedStepIndex = stagedWorkflowChain.firstIndex { $0.id == step.id }
            update(step.id) { $0.state = .running }
            // Each step carries its own model, so a chain can read a hard hand
            // with the best available and then count entities with something
            // cheap. nil means the workflow resolves its own alias.
            guard let workflowId = await resolveWorkflowId(for: step) else {
                // Could not realise this step. STOP, exactly as an engine
                // failure stops the chain — the earlier `continue` ran step
                // N+1 against an input step N never produced (review,
                // 2026-08-29).
                update(step.id) { $0.state = .failed }
                break
            }
            let threadId = await awaitWorkflowExecution(
                workflowId: workflowId,
                workflowName: step.name,
                docIds: targets,
                providerOverride: step.providerOverride,
                modelOverride: step.modelOverride,
                artifactTypeHint: artifactTypeHint,
                artifactStepNameHint: artifactStepNameHint,
                onThreadId: { threadId in
                    // Stamped the moment the server accepts, not when the run
                    // ends — the point is to watch a step WHILE it works.
                    update(step.id) { $0.threadId = threadId }
                }
            )
            // The chip states the run's OUTCOME, not merely that it returned.
            // The first version set .succeeded unconditionally, so an engine
            // failure wore a green check — the observer already knows the
            // settled status, so ask it (review fix, 2026-08-29).
            let settled = executionObserver.getExecution(threadId: threadId)?.status
            let stepSucceeded = settled == .completed
            update(step.id) { $0.state = stepSucceeded ? .succeeded : .failed }
            // A chain is sequential BECAUSE step N+1 reads what step N wrote.
            // Running the review pass after the transcription failed spends
            // money on an input that does not exist; stop and leave the later
            // chips pending so the rail shows exactly where it stopped.
            if !stepSucceeded { break }
        }
    }

    /// The workflow a step runs.
    ///
    /// A workflow step already has one. A TOOL step does not: the engine
    /// executes stored workflows only, so the tool is realised as a one-step
    /// workflow in a `/Tools` folder — created HERE, at run time, because the
    /// user pressed play, and never while merely browsing the tools popover.
    /// It is reused on later runs and is a real workflow the node editor can
    /// open, which is what makes "run a tool" honest rather than a hidden
    /// special case.
    @MainActor
    func resolveWorkflowId(for step: StagedWorkflowStep) async -> String? {
        if let workflow = step.workflow { return workflow.id }
        guard case .tool(let toolName, let displayName, _, _) = step.kind else { return nil }
        return await workflowStore.realizeToolWorkflow(
            toolName: toolName, displayName: displayName
        )
    }

    /// Identity of the current cost question: re-price when the chain, its
    /// models, or the number of targets changes — and not on every render.
    var chainCostKey: String {
        let steps = stagedWorkflowChain
            .map { "\($0.stepKey):\($0.modelOverride ?? "")" }
            .joined(separator: "|")
        return "\(steps)#\(workflowBarTargetCount)"
    }

    /// The scope, NAMED: an inspector selection names what it resolved to
    /// ("5 regions of 4_Hoja_531_Verso", "Transcription Review of …"); one
    /// document shows its display name, several show the same typed noun the
    /// status island uses ("3 images", "5 pages").
    var workflowBarTargetDetail: String? {
        let scope = workflowBarRunScope
        if let named = WorkflowBarPolicy.scopeDetail(scope) {
            return named
        }
        let ids = scope.documentIds
        guard !ids.isEmpty else { return nil }
        let docs = documentStore.currentDocuments.filter { Set(ids).contains($0.id) }
        if ids.count == 1 {
            if let doc = docs.first ?? detailDocument {
                return DocumentTitle.displayName(for: doc)
            }
            return nil
        }
        let noun: String
        if !docs.isEmpty, docs.allSatisfy({ $0.fileType == .image }) {
            noun = "images"
        } else if !docs.isEmpty, docs.allSatisfy({ $0.docType == .page }) {
            noun = "pages"
        } else if !docs.isEmpty, docs.allSatisfy({ $0.docType == .folder }) {
            noun = "folders"
        } else {
            noun = "items"
        }
        return "\(ids.count) \(noun)"
    }

    var workflowBarTargetCount: Int {
        workflowBarRunScope.documentIds.count
    }

    /// Price the staged chain as a CEILING, summed across steps.
    ///
    /// A ceiling rather than a point estimate: the models are known, the item
    /// count is known and max_tokens is an explicit bound, so an upper limit
    /// is a promise that can be kept where "about \$0.30" is guesswork. Steps
    /// the engine cannot price (no registry entry) are skipped rather than
    /// counted as zero, and the total is marked approximate.
    @MainActor
    func refreshChainCostCeiling() async {
        guard !stagedWorkflowChain.isEmpty, workflowBarTargetCount > 0 else {
            stagedChainCostCeiling = nil
            chromeUX.stagedCompareCostCeiling = nil
            return
        }
        var total = 0.0
        var priced = false
        for step in stagedWorkflowChain {
            // Only stored workflows can be priced; a tool step has no
            // workflow until the run makes one, so it is left unpriced rather
            // than guessed at.
            guard let workflowId = step.workflow?.id else { continue }
            if let cost = await workflowStore.estimateStepCost(
                workflowId: workflowId,
                fileCount: workflowBarTargetCount,
                provider: step.providerOverride,
                model: step.modelOverride
            ) {
                total += cost
                priced = true
            }
        }
        stagedChainCostCeiling = priced ? total : nil
        await refreshCompareCostCeiling()
    }

    /// Show what a step produced: the document it wrote, in whichever surface
    /// suits — Preview for a page, the Reader for its text.
    @MainActor
    func openStagedStepResult(_ step: StagedWorkflowStep) {
        // A RUNNING step opens its live trace instead of its output, because
        // it has not produced one yet (Daniel, 2026-08-28: "we should be able
        // to click when its running to see the output"). The Activity detail
        // window streams the step trace as it happens.
        // A FAILED step also opens its trace: the question a red chip raises
        // is "why", and the answer is in the run, not in the document
        // (review fix, 2026-08-29).
        if step.state == .running || step.state == .failed,
           let threadId = step.threadId {
            ActivityWindowSelectionState.shared.select(SelectedActivityRun(
                id: threadId,
                name: step.name,
                workflowId: step.workflow?.id,
                threadId: threadId,
                timestamp: Date(),
                status: step.state == .failed ? .failed : .running,
                isLive: step.state == .running,
                libraryId: windowState.libraryId,
                libraryName: windowState.library?.displayName,
                childType: nil
            ))
            openWindow(id: ActivityWindowSelectionState.detailWindowID)
            return
        }

        // The run acted on the targets FROZEN at press time — opening the
        // live selection instead showed whatever the user had wandered to
        // since (review, 2026-08-29). Falls back to the live selection for a
        // step opened before any chain has run.
        let targets = lastChainRunTargets.isEmpty
            ? workflowBarRunScope.documentIds
            : lastChainRunTargets
        guard let first = targets.first ?? detailDocument?.id,
              let doc = documentStore.currentDocuments.first(where: { $0.id == first })
        else { return }
        detailDocument = doc
        setPaneVisible(.reading, true)
    }

    /// Models a chain step can be pinned to. Read from the configured tiers
    /// rather than the full provider catalogue: these are the models the user
    /// has actually set up, which is the useful shortlist beside a chip.
    var workflowBarModelChoices: [WorkflowBarModelChoice] {
        let defaults = cachedAIDefaults
        // A named triple, not a bare tuple: three positional Strings that all
        // mean different things is exactly the shape a reader misreads.
        struct TierCandidate {
            let tier: String
            let provider: String
            let model: String
        }
        let candidates: [TierCandidate] = [
            TierCandidate(tier: "Vision", provider: defaults.visionMediumProvider,
                          model: defaults.visionMediumModel),
            TierCandidate(tier: "Text", provider: defaults.mediumProvider,
                          model: defaults.mediumModel),
            TierCandidate(tier: "Large", provider: defaults.largeProvider,
                          model: defaults.largeModel),
            TierCandidate(tier: "Small", provider: defaults.smallProvider,
                          model: defaults.smallModel)
        ]
        var seen = Set<String>()
        return candidates.compactMap { candidate in
            let model = candidate.model
            guard !model.isEmpty, !seen.contains(model) else { return nil }
            seen.insert(model)
            let short = ModelChipToolbarItem.shorten(model)
            return WorkflowBarModelChoice(
                label: "\(short)  ·  \(candidate.tier)",
                provider: candidate.provider,
                model: model
            )
        }
    }

    /// Whether a run on the current selection would go to a VISION model.
    ///
    /// Images and pages are read by a vision model; everything else by a text
    /// one. The chip states the tier the run would really use rather than one
    /// fixed "default", because the two differ and only one of them is true
    /// for what is selected.
    var selectionPrefersVisionModel: Bool {
        let scope = workflowBarRunScope
        switch scope {
        case .artifact:
            // An artifact is text an earlier step wrote — the whole point of
            // scoping to it is NOT re-reading the pixels.
            return false
        case .regions, .marqueeSelection:
            // Region nodes and marquee crops are cut from a page image; they
            // may not be in the browser's currentDocuments, so answer from
            // what a crop IS.
            return true
        case .documents, .detailDocument, .nothing:
            let ids = Set(scope.documentIds)
            let docs = documentStore.currentDocuments.filter { ids.contains($0.id) }
            if docs.isEmpty {
                guard let detail = detailDocument else { return false }
                return detail.fileType == .image || detail.docType == .page
            }
            return docs.contains { $0.fileType == .image || $0.docType == .page }
        }
    }

    /// What the bar is pointed at.
    ///
    /// Projected from the resolved run scope, so the verb filtering and the
    /// run itself can never disagree about what "the selection" means.
    var workflowBarTarget: WorkflowBarPolicy.Target {
        workflowBarRunScope.target
    }
}
