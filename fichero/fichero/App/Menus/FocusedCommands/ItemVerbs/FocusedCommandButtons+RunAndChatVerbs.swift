import SwiftUI

// MARK: - Run Workflow ▸ and Add to Chat on a selection, one component each (#5652 slice 4, group 6)

// Run Workflow ▸ (its label, what it runs on, and the refusal when nothing can be) and Add to Chat are ONE item
// each: the sidebar's row menu and the Items list's context menu render them on the clicked row, and the Project
// menu renders them on the focused Items list's selection (Workflows ▸ Run Workflow ▸, Chat ▸ Add to Chat), through
// `ItemVerbsTarget`. Each surface supplies its own workflow list (the sidebar's sections, the Items list's folders);
// the shell, the words and the run are shared.

/// What Run Workflow ▸ runs on: how many documents, whether the click fell outside the selection, and the run.
struct WorkflowRunVerbs: Equatable {
    let workflows: [WorkflowSidebarItem]
    let targetCount: Int
    var ignoredSelection = false
    let run: @MainActor (_ workflowId: String, _ provider: String?, _ model: String?) -> Void

    static func == (lhs: Self, rhs: Self) -> Bool {
        lhs.workflows.map(\.id) == rhs.workflows.map(\.id) && lhs.targetCount == rhs.targetCount
            && lhs.ignoredSelection == rhs.ignoredSelection
    }
}

extension ItemVerbs {
    static let runWorkflowTitle = "Run Workflow"
    static let addToChatTitle = "Add to Chat"
    static let nothingToRunOn = "Nothing to run on"
    static let runsOnClickedOnly = "Runs on this item only — it is outside your selection"

    /// What the menu says before the run, so a run never reaches further (or less far) than it looks.
    static func runScopeLine(targetCount: Int, ignoredSelection: Bool) -> String? {
        if ignoredSelection { return runsOnClickedOnly }
        return targetCount > 1 ? "Runs on \(targetCount) documents" : nil
    }

    static func runWorkflowReason(_ target: ItemVerbsTarget?) -> String? {
        guard let runs = target?.runWorkflow else { return "Select documents in Items to run a workflow on them" }
        if runs.workflows.isEmpty { return "This project has no workflow to run" }
        return runs.targetCount == 0 ? nothingToRunOn : nil
    }

    static func addToChatReason(_ target: ItemVerbsTarget?) -> String? {
        guard let target, !target.ids.isEmpty else { return nothingSelected }
        return target.addToChat == nil ? "Only documents can be added to a chat" : nil
    }
}

/// Run Workflow ▸, as ONE item: the shell every surface renders, with the surface's own workflow list inside.
struct RunWorkflowMenuItem<Workflows: View>: View {
    let targetCount: Int
    var ignoredSelection = false
    @ViewBuilder let workflows: () -> Workflows

    var body: some View {
        Menu {
            if targetCount == 0 {
                Button(ItemVerbs.nothingToRunOn) {}
                    .disabled(true)
            } else {
                if let line = ItemVerbs.runScopeLine(targetCount: targetCount, ignoredSelection: ignoredSelection) {
                    Text(line)
                    Divider()
                }
                workflows()
            }
        } label: {
            Label(ItemVerbs.runWorkflowTitle, systemImage: "flowchart")
        }
    }
}

/// Add to Chat, as ONE item: the sidebar's and the Items list's menus and Project › Chat.
struct AddToChatMenuItem: View {
    let add: (@MainActor () -> Void)?

    var body: some View {
        Button { add?() } label: {
            Label(ItemVerbs.addToChatTitle, systemImage: "bubble.left.and.text.bubble.right")
        }
        .disabled(add == nil)
    }
}

// MARK: - The menu bar (Project)

/// Project › Workflows ▸ Run Workflow ▸ on the focused Items list's selection.
struct FocusedRunWorkflowMenu: View {
    @FocusedValue(\.itemVerbs) private var items

    var body: some View {
        if let runs = items?.runWorkflow, ItemVerbs.runWorkflowReason(items) == nil {
            RunWorkflowMenuItem(targetCount: runs.targetCount) {
                RunWorkflowSubmenuItems(workflows: runs.workflows) { workflowId, provider, model in
                    runs.run(workflowId, provider, model)
                }
            }
        } else {
            Menu(ItemVerbs.runWorkflowTitle) {}
                .disabled(true)
            if let reason = ItemVerbs.runWorkflowReason(items) { Text(reason) }
        }
    }
}

/// Project › Chat ▸ Add to Chat on the focused selection.
struct FocusedAddToChatButton: View {
    @FocusedValue(\.itemVerbs) private var items

    var body: some View {
        AddToChatMenuItem(add: items?.addToChat)
        if let reason = ItemVerbs.addToChatReason(items) { Text(reason) }
    }
}
