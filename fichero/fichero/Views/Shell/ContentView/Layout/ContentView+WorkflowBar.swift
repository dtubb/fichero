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
                showsLabels: showWorkflowBarLabels,
                onRun: { workflowId, provider, model in
                    runWorkflowOnSelection(
                        workflowId: workflowId,
                        providerOverride: provider,
                        modelOverride: model
                    )
                }
            )
        }
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
