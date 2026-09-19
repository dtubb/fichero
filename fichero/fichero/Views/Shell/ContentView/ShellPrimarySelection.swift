import Foundation

/// The ONE answer to "which selected row is primary" at the shell boundary
/// (2026-08-09, the selection-identity contract): first match in the given
/// DOCUMENT ORDER — the order the user sees — falling back to the stable
/// lexical minimum for ids not in the loaded list (restore-before-load).
/// Never `Set.first`: hash order made the promoted preview, the entity
/// focus, and the stale-fetch guard each capable of drawing a DIFFERENT
/// element from the same multi-selection.
func shellPrimarySelectionId(in selection: Set<String>, orderedBy documents: [Document]) -> String? {
    guard !selection.isEmpty else { return nil }
    if let inOrder = documents.first(where: { selection.contains($0.id) }) {
        return inOrder.id
    }
    return selection.min()
}

/// #4882 (spec: workflows.selection.library-row-opens-editor): the ONE
/// EFFECTIVE workflow selection, from EITHER axis, without touching
/// `AppViewMode` or the sidebar path. `ContentView.activeWorkflowItem` is
/// this value — every mode-gated "is the window in workflow mode?" site was
/// rewritten to ask that instead, so the sidebar and Library paths share one
/// load, one autosave and one Inspector, not two of each (#4882 follow-up,
/// after the first delivery of this fix was reverted for a stale-load /
/// lost-autosave bug the mode-only gate caused).
///
/// The sidebar's own `viewMode == .workflow(_)` still wins first, unchanged
/// (`routeWorkflowMirrorSelection` sets it — nothing about that path
/// changes). The NEW case this finding asks for: a Library row whose single
/// selection is a workflow mirror document, with `viewMode` staying
/// `.library` — "selecting a workflow shows its editor, no mode flip, no
/// double-click." `singleSelectedDocument` is resolved by the CALLER (the
/// same `shellPrimarySelectionId(in:orderedBy:)` tier `documentForCanvas`
/// already uses for its own "selected" tier), and must be `nil` for a
/// multi-selection — this function does not itself guard against more than
/// one selected row; that is the caller's contract to uphold, exactly as
/// `documentForCanvas`'s own callers uphold theirs.
func workflowCanvasSelection(
    viewMode: AppViewMode,
    singleSelectedDocument: Document?,
    workflows: [WorkflowSidebarItem]
) -> WorkflowSidebarItem? {
    if case .workflow(let selected) = viewMode, let selected {
        return selected
    }
    guard let doc = singleSelectedDocument, doc.isWorkflowNode else { return nil }
    return sidebarWorkflowDestination(for: doc, workflows: workflows)
}
