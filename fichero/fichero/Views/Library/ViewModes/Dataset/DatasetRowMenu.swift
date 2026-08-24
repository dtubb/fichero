import SwiftUI

// MARK: - The ONE dataset row menu (parity audit, 2026-08-23)

/// Every dataset renderer's right-click menu, in one place.
///
/// Grid, Cards, Calendar, Timeline and Map each carried a private copy, and
/// they had drifted into four different menus: Cards offered exclusion and
/// Run Workflow, Grid offered Run Workflow without exclusion, Calendar offered
/// Edit Date without either, Timeline offered two verbs and Map offered one.
/// Same rows, same library, different actions depending on which renderer you
/// happened to be looking at — Daniel, 2026-08-23: "make sure all library views
/// are following the same code paths."
///
/// **Why this is not `documentContextMenu(for:)`.** A dataset row's vocabulary
/// is deliberately narrower than a browse row's: Edit Date belongs here and
/// duplicate/alias arguably do not, and widening what five menus offer is a
/// product decision rather than a consolidation. So this takes the same shape —
/// a row plus its capabilities, emitting sections — and full adoption later is
/// a swap rather than a rewrite.
///
/// **Capabilities, not flags.** A renderer passes what it HAS (a date column, a
/// document service, workflows) and the menu decides what to show. A renderer
/// that simply forgot to pass something therefore offers less, visibly, rather
/// than silently doing something different from its siblings.
struct DatasetRowMenu: View {
    /// The rows this click targets. One for a row click; a day's worth for a
    /// calendar cell.
    let rows: [DatasetPage.Row]
    /// The batch a verb applies to: the selection when the clicked row is in
    /// it, else just the clicked row — the Finder rule, shared so the five
    /// renderers cannot disagree about it.
    let targets: [String]
    /// Nil = no date column, or no service to write one; the item is hidden.
    var canEditDate: Bool = false
    /// Nil = exclusion items hidden (previews, closed library).
    var documentService: DocumentService?
    var workflows: [WorkflowSidebarItem] = []

    var onOpen: (DatasetPage.Row) -> Void
    var onOpenSource: (DatasetPage.Row) -> Void
    var onEditDate: (DatasetPage.Row) -> Void = { _ in }
    var onRunWorkflow: (String, [String], String?, String?) -> Void = { _, _, _, _ in }

    var body: some View {
        openItems
        editDateItem
        exclusionItems
        runWorkflowItem
    }

    /// One Open per row, named when there is more than one — a calendar cell
    /// holds a day, and "Open" alone would not say which entry.
    @ViewBuilder
    private var openItems: some View {
        if rows.count == 1, let row = rows.first {
            Button("Open") { onOpen(row) }
        } else {
            ForEach(rows) { row in
                Button("Open \(row.name)") { onOpen(row) }
            }
        }
        if let first = rows.first, first.parentId != nil {
            // THE REFERENCE (Daniel 2026-08-15): an extracted row is one click
            // from the page it came from.
            Button("Show Source Page") { onOpenSource(first) }
        }
    }

    @ViewBuilder
    private var editDateItem: some View {
        if canEditDate, let first = rows.first {
            Button("Edit Date…") { onEditDate(first) }
        }
    }

    /// Exclusion parity with the browse views (Daniel, 2026-08-19): dataset
    /// rows are nodes like any other, so bulk curation works here too.
    @ViewBuilder
    private var exclusionItems: some View {
        if let documentService, !targets.isEmpty {
            Divider()
            Button("Exclude from Processing") {
                Task { _ = try? await documentService.batchExclude(
                    documentIds: targets, excluded: true, scope: .processing) }
            }
            Button("Exclude from Search") {
                Task { _ = try? await documentService.batchExclude(
                    documentIds: targets, excluded: true, scope: .search) }
            }
            Button("Include Everywhere") {
                Task {
                    _ = try? await documentService.batchExclude(
                        documentIds: targets, excluded: false, scope: .processing)
                    _ = try? await documentService.batchExclude(
                        documentIds: targets, excluded: false, scope: .search)
                }
            }
        }
    }

    /// The scope is stated BEFORE the click (2026-08-15): a batch names what it
    /// will run on rather than reporting it afterwards.
    @ViewBuilder
    private var runWorkflowItem: some View {
        if !workflows.isEmpty, !targets.isEmpty {
            Divider()
            Menu("Run Workflow") {
                if targets.count > 1 {
                    Text("Runs on \(targets.count) entries")
                    Divider()
                }
                RunWorkflowSubmenuItems(workflows: workflows) { workflowId, provider, model in
                    onRunWorkflow(workflowId, targets, provider, model)
                }
            }
        }
    }
}
