import Foundation
@testable import Fichero
import Testing

/// #5652 slice 4, group 6: Run Workflow ▸ (its shell: the scope it says before the run, and its refusal) and Add to
/// Chat are one item each, which the sidebar's row menu and the Items list's context menu render on the clicked
/// row, and Project › Workflows ▸ / Chat ▸ render on the focused Items list's selection. What breaks without these:
/// a run that reaches further than the menu says, a run offered with nothing to run on, or Add to Chat on folders.
@MainActor
@Suite("Run Workflow ▸ and Add to Chat, one component each (#5652 slice 4)")
struct RunAndChatMenuTests {
    private let page = Document(id: "p1", docType: .file, fileType: .image, name: "0970.jpg")

    @Test("the menu says what a run reaches before the click")
    func scopeLine() {
        #expect(ItemVerbs.runScopeLine(targetCount: 1, ignoredSelection: false) == nil)
        #expect(ItemVerbs.runScopeLine(targetCount: 63, ignoredSelection: false) == "Runs on 63 documents")
        #expect(ItemVerbs.runScopeLine(targetCount: 1, ignoredSelection: true) == ItemVerbs.runsOnClickedOnly)
    }

    @Test("Project › Workflows ▸ Run Workflow ▸ says why it cannot run")
    func runReasons() {
        #expect(ItemVerbs.runWorkflowReason(nil) == "Select documents in Items to run a workflow on them")
        var target = ItemVerbsTarget(ids: ["p1"], documents: [page])
        target.runWorkflow = WorkflowRunVerbs(workflows: [], targetCount: 1) { _, _, _ in }
        #expect(ItemVerbs.runWorkflowReason(target) == "This project has no workflow to run")
        target.runWorkflow = WorkflowRunVerbs(workflows: Self.workflows, targetCount: 0) { _, _, _ in }
        #expect(ItemVerbs.runWorkflowReason(target) == ItemVerbs.nothingToRunOn)
        target.runWorkflow = WorkflowRunVerbs(workflows: Self.workflows, targetCount: 2) { _, _, _ in }
        #expect(ItemVerbs.runWorkflowReason(target) == nil)
    }

    @Test("a run from the bar reaches the Items list's one run, with the workflow and its overrides")
    func runReachesTheList() {
        var runs: [String] = []
        let verbs = WorkflowRunVerbs(workflows: Self.workflows, targetCount: 2) { id, provider, model in
            runs.append("\(id)|\(provider ?? "-")|\(model ?? "-")")
        }
        verbs.run("wf-1", "anthropic", nil)
        #expect(runs == ["wf-1|anthropic|-"])
    }

    @Test("Add to Chat acts on documents, and says so on anything else")
    func addToChat() {
        #expect(ItemVerbs.addToChatReason(nil) == ItemVerbs.nothingSelected)
        var target = ItemVerbsTarget(ids: ["f1"], documents: [])
        #expect(ItemVerbs.addToChatReason(target) == "Only documents can be added to a chat")
        var added = 0
        target.addToChat = { added += 1 }
        #expect(ItemVerbs.addToChatReason(target) == nil)
        target.addToChat?()
        #expect(added == 1)
    }

    @Test("the target compares by the run's reach and the workflows, so the same selection does not republish")
    func equality() {
        let lhs = WorkflowRunVerbs(workflows: Self.workflows, targetCount: 2) { _, _, _ in }
        #expect(lhs == WorkflowRunVerbs(workflows: Self.workflows, targetCount: 2) { _, _, _ in })
        #expect(lhs != WorkflowRunVerbs(workflows: Self.workflows, targetCount: 3) { _, _, _ in })
    }

    private static var workflows: [WorkflowSidebarItem] {
        [WorkflowSidebarItem(id: "wf-1", name: "Transcribe")]
    }
}
