//
//  WorkflowStepRunGlanceTests.swift
//  FicheroTests
//
//  #5564: the maintainer, watching a run, found the workflow bar's step
//  popover listed too much (every node of the workflow and its prompts). It
//  now shows ONLY the step running now (its name, the page by file name, its
//  state and why) or, when nothing runs, the chain's recent errors with their
//  reasons, newest first; everything else is behind "Details".
//
//  Spec: docs/contributor_manual/specs/ui/workflows.md,
//  `workflows.bar.step-popover-run-glance`. Written from that line.
//
//  The trees are the engine's own JSON shape (`GET /api/activity/jobs/{run}`,
//  as recorded in ActivityTableTests), decoded by the generated client, so the
//  glance reads what the app really holds in `ActivityStore.runTrees`.
//
//  Not covered: a mounted popover drawing the value, and the Details click
//  opening the window (no mounted-view harness in this target).
//

@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

struct WorkflowStepRunGlanceTests {

    // MARK: - Fixtures

    private static func step(
        _ name: String, state: StagedStepState = .pending, threadId: String? = nil
    ) -> StagedWorkflowStep {
        StagedWorkflowStep(
            kind: .workflow(WorkflowSidebarItem(id: "wf-\(name)", name: name)),
            state: state,
            threadId: threadId
        )
    }

    private static func tree(_ json: String) throws -> ActivityJobNode {
        ActivityJobNode(try JSONDecoder().decode(Components.Schemas.JobTree.self, from: Data(json.utf8)))
    }

    private static func node(
        id: String, kind: String, subject: String, state: String, parent: String?,
        reason: String? = nil, displayName: String? = nil, account: String? = nil, children: [String] = []
    ) -> String {
        func quoted(_ text: String?) -> String { text.map { "\"\($0)\"" } ?? "null" }
        return """
        {"id": "\(id)", "kind": "\(kind)", "name": "Step", "subject": "\(subject)",
         "display_name": \(quoted(displayName)), "model": null, "state": "\(state)",
         "reason": \(quoted(reason)), "parent_id": \(quoted(parent)),
         "done": 0, "total": 0, "failed": 0, "seconds": null, "tokens": 0, "cost_usd": null,
         "unpriced_models": [], "account": \(account ?? "null"),
         "children": [\(children.joined(separator: ", "))]}
        """
    }

    /// A run on its "Read" step, one page done and one waiting for memory.
    private static func waitingRunTree(_ run: String = "run-1") throws -> ActivityJobNode {
        try tree(node(id: run, kind: "workflow", subject: run, state: "running", parent: nil, children: [
            node(id: "\(run):Files", kind: "workflow-step", subject: "\(run):Files", state: "done", parent: run),
            node(id: "\(run):Read", kind: "workflow-step", subject: "\(run):Read", state: "running", parent: run,
                 children: [
                    node(id: "p1", kind: "page", subject: "doc-1", state: "done", parent: "\(run):Read",
                         displayName: "SM_NPQ_C01_003.jpg"),
                    node(id: "p2", kind: "page", subject: "doc-2", state: "waiting", parent: "\(run):Read",
                         reason: "Waiting for memory: needs 3.9 GB, 2.2 GB free",
                         displayName: "SM_NPQ_C01_004.jpg")
                 ])
        ]))
    }

    // MARK: - While the run works: only the step running now

    @Test("while a step waits, the popover names the step, the page by file name, its state and why")
    func runningShowsStepPageStateAndWhy() throws {
        let running = Self.step("Transcribe", state: .running, threadId: "run-1")
        let pending = Self.step("Entities")
        let glance = WorkflowStepRunGlance.make(
            step: pending, chain: [running, pending], trees: ["run-1": try Self.waitingRunTree()]
        )
        #expect(glance == .running(.init(
            threadId: "run-1", workflow: "Transcribe", step: "Read", page: "SM_NPQ_C01_004.jpg",
            state: "Waiting", reason: "Waiting for memory: needs 3.9 GB, 2.2 GB free"
        )))
        #expect(glance.detailsThreadId == "run-1", "Details opens the running run")
    }

    @Test("a running page wins over a waiting one, and a running page says no reason")
    func runningPageWinsOverWaiting() throws {
        let tree = try Self.tree(Self.node(id: "r", kind: "workflow", subject: "r", state: "running", parent: nil,
            children: [Self.node(id: "r:Read", kind: "workflow-step", subject: "r:Read", state: "running", parent: "r",
                children: [
                    Self.node(id: "a", kind: "page", subject: "d1", state: "waiting", parent: "r:Read",
                              reason: "Waiting: memory is tight", displayName: "a.jpg"),
                    Self.node(id: "b", kind: "page", subject: "d2", state: "running", parent: "r:Read",
                              displayName: "b.jpg")
                ])]))
        let now = WorkflowStepRunGlance.now(workflow: "Transcribe", threadId: "r", tree: tree)
        #expect(now.page == "b.jpg")
        #expect(now.state == "Running")
        #expect(now.reason == nil)
    }

    @Test("a run whose tree has not arrived still says which step runs, and nothing it does not know")
    func runningWithoutTreeSaysOnlyTheStep() {
        let running = Self.step("Transcribe", state: .running, threadId: "run-1")
        let glance = WorkflowStepRunGlance.make(step: running, chain: [running], trees: [:])
        #expect(glance == .running(.init(
            threadId: "run-1", workflow: "Transcribe", step: nil, page: nil, state: "Running", reason: nil
        )))
    }

    @Test("the running glance wins on every chip of the chain, even a finished one")
    func runningWinsOverErrors() throws {
        let failed = Self.step("Transcribe", state: .failed, threadId: "run-0")
        let running = Self.step("Entities", state: .running, threadId: "run-1")
        let glance = WorkflowStepRunGlance.make(
            step: failed, chain: [failed, running], trees: ["run-1": try Self.waitingRunTree()]
        )
        guard case .running(let now) = glance else {
            Issue.record("expected the running glance, got \(glance)")
            return
        }
        #expect(now.workflow == "Entities")
    }

    // MARK: - Nothing running: only the recent errors, newest first

    @Test("when nothing runs, the errors are the run's failed pages with their reasons, newest first, at most three")
    func failedShowsNewestErrorsFirst() throws {
        let account = """
        {"state": "done", "pages_total": 5, "pages_done": 1, "pages_failed": 4, "pages_left": 0,
         "failures": [
           {"page": "p1.jpg", "reason": "first"}, {"page": "p2.jpg", "reason": "second"},
           {"page": "p3.jpg", "reason": "third"}, {"page": "p4.jpg", "reason": "fourth"}
         ], "waiting_reason": null, "reason": null, "interrupted": false}
        """
        let tree = try Self.tree(Self.node(id: "run-1", kind: "workflow", subject: "run-1", state: "done",
                                           parent: nil, account: account))
        let done = Self.step("Transcribe", state: .succeeded, threadId: "run-1")
        let glance = WorkflowStepRunGlance.make(step: done, chain: [done], trees: ["run-1": tree])
        guard case .failed(let failures) = glance else {
            Issue.record("expected recent errors, got \(glance)")
            return
        }
        #expect(failures.map(\.page) == ["p4.jpg", "p3.jpg", "p2.jpg"])
        #expect(failures.map(\.reason) == ["fourth", "third", "second"])
        #expect(glance.detailsThreadId == "run-1")
    }

    @Test("without an account, the tree's failed pages are the errors, named by file")
    func failedPagesFromTreeWithoutAccount() throws {
        let tree = try Self.tree(Self.node(id: "r", kind: "workflow", subject: "r", state: "failed", parent: nil,
            reason: "Step 'Read' failed",
            children: [Self.node(id: "r:Read", kind: "workflow-step", subject: "r:Read", state: "failed", parent: "r",
                children: [Self.node(id: "x", kind: "page", subject: "d1", state: "failed", parent: "r:Read",
                                     reason: "the provider refused this letter", displayName: "letter.jpg")])]))
        let failures = WorkflowStepRunGlance.failures(threadId: "r", state: .failed, tree: tree)
        #expect(failures.map(\.page) == ["letter.jpg"])
        #expect(failures.map(\.reason) == ["the provider refused this letter"])
    }

    @Test("a run that failed as a whole gives its own reason; one with none says so rather than nothing")
    func runLevelFailure() throws {
        let tree = try Self.tree(Self.node(id: "r", kind: "workflow", subject: "r", state: "failed", parent: nil,
                                           reason: "Kraken is not installed"))
        #expect(WorkflowStepRunGlance.failures(threadId: "r", state: .failed, tree: tree).map(\.reason)
            == ["Kraken is not installed"])
        #expect(WorkflowStepRunGlance.failures(threadId: "r", state: .failed, tree: nil).map(\.reason)
            == [WorkflowStepRunGlance.noReason])
    }

    @Test("the errors are the whole chain's: the later step's are newer")
    func chainErrorsNewestStepFirst() {
        let first = Self.step("Transcribe", state: .failed, threadId: "run-0")
        let second = Self.step("Entities", state: .failed, threadId: "run-1")
        let glance = WorkflowStepRunGlance.make(step: first, chain: [first, second], trees: [:])
        guard case .failed(let failures) = glance else {
            Issue.record("expected recent errors, got \(glance)")
            return
        }
        #expect(failures.map(\.threadId) == ["run-1", "run-0"])
        #expect(glance.detailsThreadId == "run-1", "Details opens the run of the newest error")
    }

    // MARK: - Idle

    @Test("a chain that ran with no errors says it finished, with Details")
    func finishedWithoutErrors() {
        let done = Self.step("Transcribe", state: .succeeded, threadId: "run-1")
        let glance = WorkflowStepRunGlance.make(step: done, chain: [done], trees: [:])
        #expect(glance == .finished(threadId: "run-1"))
        #expect(glance.detailsThreadId == "run-1")
    }

    @Test("a step that has not run keeps its 'what it does' view, with no Details")
    func notRunKeepsWhatItDoes() {
        let pending = Self.step("Transcribe")
        let glance = WorkflowStepRunGlance.make(step: pending, chain: [pending], trees: [:])
        #expect(glance == .notRun)
        #expect(glance.detailsThreadId == nil)
    }
}
