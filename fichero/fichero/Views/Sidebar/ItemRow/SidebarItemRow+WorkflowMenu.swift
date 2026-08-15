import SwiftUI

// Run Workflow menu: target resolution, section split, and the submenu that
// fires the run. Split from +Presentation.swift at the 400-line limit
// (2026-08-15); same members, only the file moved. Members are internal, not
// private — `rowContextMenu` in +Presentation.swift still calls them, and
// `private` is file-scoped in Swift.
extension SidebarItemRow {

    /// #4275 — the workflow list the Run Workflow submenu offers for this row.
    ///
    /// A row's own library store is authoritative (its list is what the run
    /// executes against, #3820). But a non-global library whose store hasn't
    /// loaded (or failed to load) used to make the submenu silently VANISH on
    /// its folders. Fall back to the global library's list so the menu is
    /// never silently empty; the run still targets this row's documents in
    /// this row's library, and a genuinely unknown workflow id surfaces the
    /// engine's error on the banner rather than nothing at all.
    ///
    /// #4450 — the fallback is filtered to `isSystem`. A global-library USER
    /// workflow (built while Global was open, or a preset DEMOTED by editing
    /// it, #780) is not a default; `resolve_default_workflow` refuses it from
    /// another library, so offering it is the menu asserting availability it
    /// has not established.
    nonisolated static func contextMenuWorkflows(
        own: [WorkflowSidebarItem],
        global: [WorkflowSidebarItem]
    ) -> [WorkflowSidebarItem] {
        own.isEmpty ? global.filter(\.isSystem) : own
    }

    /// #4450 — the two groups: global defaults, visible and runnable in EVERY
    /// library, and this library's own. Both come from ONE list: a non-global
    /// library's `/api/workflows` already merges the shipped defaults in
    /// server-side (`list_global_default_workflows`), so re-reading the global
    /// store here would list every default twice. The split is `isSystem`, the
    /// flag only the seeder writes.
    nonisolated static func workflowMenuSections(
        _ workflows: [WorkflowSidebarItem]
    ) -> (defaults: [WorkflowSidebarItem], libraryOwn: [WorkflowSidebarItem]) {
        (workflows.filter(\.isSystem), workflows.filter { !$0.isSystem })
    }

    /// One group of the Run Workflow menu. Both sections run the SAME action
    /// against the SAME targets — the split is presentational.
    @ViewBuilder
    func workflowSubmenu(
        _ workflows: [WorkflowSidebarItem],
        resolution: WorkflowRunTargetResolver.Resolution
    ) -> some View {
        RunWorkflowSubmenuItems(workflows: workflows) { workflowId, provider, model in
            // Scope provenance at the moment of fire (2026-08-15): a 63-doc
            // run from a one-row right-click was undiagnosable because the
            // request records WHAT ran, not WHY it was that wide. One line
            // names the domains so the next report answers itself.
            sidebarRowLogger.info(
                """
                contextMenu run: clicked=\(item.id, privacy: .public) \
                targets=\(resolution.targetIds.count) \
                sidebarSel=\(selectedDestinations.count) \
                windowSel=\(windowState.liveDocumentSelection.count) \
                ignoredSelection=\(resolution.ignoredSelection)
                """
            )
            runWorkflowOnDocuments(
                workflowId: workflowId,
                docIds: resolution.targetIds,
                providerOverride: provider,
                modelOverride: model
            )
        }
    }

    /// #4419: resolves against the row's own identity first, so a row in a
    /// library whose store this view does not hold still runs. `documents` is
    /// only ever an EXPANSION hint for folders now — never a membership gate —
    /// so an unloaded or cross-library store degrades to "run this row" instead
    /// of to nothing.
    var resolvedWorkflowRun: WorkflowRunTargetResolver.Resolution {
        guard let clickedTarget = workflowRunTarget(for: item) else {
            return WorkflowRunTargetResolver.Resolution(
                targetIds: [],
                ignoredSelection: false,
                usedRowIdentityFallback: false
            )
        }
        // #4523 LAW: the run's selection is the WINDOW's document selection,
        // not just the sidebar's own. The library-pane selection (live or
        // preserved across the navigation that cleared it, #712 carve-out)
        // is what makes right-clicking the selected file's row run THAT file
        // rather than its peers.
        //
        // #4552: these two are separate DOMAINS and must not be unioned. See
        // `selectionScope` — a union let the clicked row arrive from one
        // domain while the extra targets came from the other, which `resolve`
        // cannot tell apart from a real multi-selection. That ran a workflow
        // on a PDF the user had not touched in an hour.
        let sidebarSelection = Set(selectedDestinations.compactMap(workflowRunTarget(for:)))
        // LIVE pane selection only (2026-08-15): a stale preserved snapshot
        // containing the clicked file once ran a one-file job on 200 siblings.
        let windowSelection = Set(
            windowState.liveDocumentSelection.map { WorkflowRunTarget.file($0) }
        )
        return WorkflowRunTargetResolver.resolve(
            clicked: clickedTarget,
            selection: WorkflowRunTargetResolver.selectionScope(
                clicked: clickedTarget,
                sidebarSelection: sidebarSelection,
                windowSelection: windowSelection
            ),
            documents: documentStore?.sidebarDocuments ?? []
        )
    }

    func workflowRunTarget(for item: SidebarItem) -> WorkflowRunTarget? {
        guard case .document(let document) = item.itemType else { return nil }
        return document.docType == .folder ? .folder(document.id) : .file(document.id)
    }

    func workflowRunTarget(for destination: SidebarDestination) -> WorkflowRunTarget? {
        guard case .document = destination,
              let item = lookupItem(destination.serializedID) else {
            return nil
        }
        return workflowRunTarget(for: item)
    }
}
