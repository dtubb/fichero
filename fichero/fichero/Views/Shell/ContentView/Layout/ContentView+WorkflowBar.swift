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
                tools: Array(workflowStore.toolRegistry.values)
            )
            .task(id: chainCostKey) { await refreshChainCostCeiling() }
            .task {
                // Refresh when the bar appears rather than at launch: the menu
                // is only consulted here, and a stale tier would offer a model
                // the user has since changed.
                if let loaded = try? await appState.fetchAIDefaults() {
                    cachedAIDefaults = loaded
                }
            }
        }
    }

    /// Run the staged chain, one step after another on the same selection.
    ///
    /// Sequential, not fire-and-forget: step two should read what step one
    /// wrote (transcribe then clean up then catalogue), so each awaits the
    /// one before it. The engine stores chains but does not execute them, so
    /// the ordering lives here.
    ///
    /// The chain is NOT cleared on completion — a run you can repeat on the
    /// next folder is the point of having assembled it.
    @MainActor
    func runStagedChain() async {
        guard !stagedWorkflowChain.isEmpty, !isRunningStagedChain else { return }
        isRunningStagedChain = true
        defer {
            isRunningStagedChain = false
            runningStagedStepIndex = nil
        }

        // Freeze the targets ONCE. Selection can move while a long chain runs,
        // and step four landing on documents the user picked mid-run is the
        // kind of surprise a paid job must never spring.
        let targets = effectiveWorkflowRunSelection.isEmpty
            ? (detailDocument.map { [$0.id] } ?? [])
            : effectiveWorkflowRunSelection
        guard !targets.isEmpty else { return }

        // Every step starts pending again, so a re-run does not show last
        // time's greens while this time's work is still ahead.
        for index in stagedWorkflowChain.indices {
            stagedWorkflowChain[index].state = .pending
        }

        for (index, step) in stagedWorkflowChain.enumerated() {
            runningStagedStepIndex = index
            stagedWorkflowChain[index].state = .running
            // Each step carries its own model, so a chain can read a hard hand
            // with the best available and then count entities with something
            // cheap. nil means the workflow resolves its own alias.
            guard let workflowId = await resolveWorkflowId(for: step) else {
                // Could not realise this step — say so on the chip rather than
                // skipping silently and letting the chain look successful.
                if stagedWorkflowChain.indices.contains(index) {
                    stagedWorkflowChain[index].state = .failed
                }
                continue
            }
            await awaitWorkflowExecution(
                workflowId: workflowId,
                workflowName: step.name,
                docIds: targets,
                providerOverride: step.providerOverride,
                modelOverride: step.modelOverride,
                onThreadId: { threadId in
                    // Stamped the moment the server accepts, not when the run
                    // ends — the point is to watch a step WHILE it works.
                    if stagedWorkflowChain.indices.contains(index) {
                        stagedWorkflowChain[index].threadId = threadId
                    }
                }
            )
            // awaitWorkflowExecution settles the run before returning, so
            // reaching here means this step is done. Failures surface through
            // the execution observer; the chip states completion either way
            // rather than staying blue forever.
            if stagedWorkflowChain.indices.contains(index) {
                stagedWorkflowChain[index].state = .succeeded
            }
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

        // Reuse the one we made last time rather than accumulating duplicates.
        if let existing = workflowStore.workflows.first(where: {
            $0.folderPath == "/Tools" && $0.name == displayName
        }) {
            return existing.id
        }
        do {
            let created = try await workflowStore.workflowService.createToolWorkflow(
                toolName: toolName,
                displayName: displayName
            )
            await workflowStore.loadWorkflows()
            return created
        } catch {
            barLogger.error(
                "Could not realise tool \(toolName) as a workflow: \(String(describing: error))"
            )
            return nil
        }
    }

    /// Identity of the current cost question: re-price when the chain, its
    /// models, or the number of targets changes — and not on every render.
    var chainCostKey: String {
        let steps = stagedWorkflowChain
            .map { "\($0.stepKey):\($0.modelOverride ?? "")" }
            .joined(separator: "|")
        return "\(steps)#\(workflowBarTargetCount)"
    }

    var workflowBarTargetCount: Int {
        let effective = effectiveWorkflowRunSelection
        if !effective.isEmpty { return effective.count }
        return detailDocument == nil ? 0 : 1
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
            return
        }
        var total = 0.0
        var priced = false
        for step in stagedWorkflowChain {
            // Only stored workflows can be priced; a tool step has no
            // workflow until the run makes one, so it is left unpriced rather
            // than guessed at.
            guard let workflowId = step.workflow?.id else { continue }
            if let cost = try? await workflowStore.workflowService.estimateCost(
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
    }

    /// Show what a step produced: the document it wrote, in whichever surface
    /// suits — Preview for a page, the Reader for its text.
    @MainActor
    func openStagedStepResult(_ step: StagedWorkflowStep) {
        // A RUNNING step opens its live trace instead of its output, because
        // it has not produced one yet (Daniel, 2026-08-28: "we should be able
        // to click when its running to see the output"). The Activity detail
        // window streams the step trace as it happens.
        if step.state == .running, let threadId = step.threadId {
            ActivityWindowSelectionState.shared.select(SelectedActivityRun(
                id: threadId,
                name: step.name,
                workflowId: step.workflow?.id,
                threadId: threadId,
                timestamp: Date(),
                status: .running,
                isLive: true,
                libraryId: windowState.libraryId,
                libraryName: windowState.library?.displayName,
                childType: nil
            ))
            openWindow(id: ActivityWindowSelectionState.detailWindowID)
            return
        }

        // The run acted on the frozen targets, so the first of them is what
        // this step wrote to. Opening the SELECTION rather than a run record
        // is what the user means by "see it in preview or reader".
        let targets = effectiveWorkflowRunSelection
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
        let candidates: [(String, String, String)] = [
            ("Vision", defaults.visionMediumProvider, defaults.visionMediumModel),
            ("Text", defaults.mediumProvider, defaults.mediumModel),
            ("Large", defaults.largeProvider, defaults.largeModel),
            ("Small", defaults.smallProvider, defaults.smallModel)
        ]
        var seen = Set<String>()
        return candidates.compactMap { tier, provider, model in
            guard !model.isEmpty, !seen.contains(model) else { return nil }
            seen.insert(model)
            let short = model.split(separator: "/").last.map(String.init) ?? model
            return WorkflowBarModelChoice(
                label: "\(short)  ·  \(tier)",
                provider: provider,
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
        let ids = Set(effectiveWorkflowRunSelection)
        let docs = documentStore.currentDocuments.filter { ids.contains($0.id) }
        if docs.isEmpty {
            guard let detail = detailDocument else { return false }
            return detail.fileType == .image || detail.docType == .page
        }
        return docs.contains { $0.fileType == .image || $0.docType == .page }
    }

    /// What the bar is pointed at.
    ///
    /// Reads the same accessor every other launch surface reads (#4523), so
    /// the bar cannot disagree with the Run menu about what "the selection"
    /// means — and falls back to the previewed document, which is what makes
    /// the bar useful while reading a single page with nothing list-selected.
    var workflowBarTarget: WorkflowBarPolicy.Target {
        let effective = effectiveWorkflowRunSelection
        if !effective.isEmpty {
            return .documents(count: effective.count)
        }
        if detailDocument != nil {
            return .documents(count: 1)
        }
        return .nothing
    }
}
