import SwiftUI

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
                showsLabels: showWorkflowBarLabels,
                staged: $stagedWorkflowChain,
                onRunChain: { Task { await runStagedChain() } },
                isRunning: isRunningStagedChain
            )
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
        defer { isRunningStagedChain = false }

        // Freeze the targets ONCE. Selection can move while a long chain runs,
        // and step four landing on documents the user picked mid-run is the
        // kind of surprise a paid job must never spring.
        let targets = effectiveWorkflowRunSelection.isEmpty
            ? (detailDocument.map { [$0.id] } ?? [])
            : effectiveWorkflowRunSelection
        guard !targets.isEmpty else { return }

        for workflow in stagedWorkflowChain {
            await awaitWorkflowExecution(
                workflowId: workflow.id,
                workflowName: workflow.name,
                docIds: targets
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
