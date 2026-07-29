@testable import Fichero
import Foundation
import XCTest

/// Reconcile rule for cross-window workflow node-config sync (#2278). Covers the
/// three outcomes plus the no-baseline safety case — no live backend needed
/// because `WorkflowSync.decide` is pure.
final class WorkflowSyncTests: XCTestCase {

    private func makeWorkflow(id: String = "wf-1", model: String) -> Workflow {
        var workflow = Workflow(id: id, name: "Test", description: "")
        // `model` stands in for any node-config field: two definitions with
        // different models are `!=` under the synthesized Equatable.
        workflow.model = model
        return workflow
    }

    /// A foreign change while the local copy is clean (equals the baseline) is
    /// adopted.
    func testForeignChangeWhileCleanApplies() {
        let baseline = makeWorkflow(model: "gpt-a")
        let local = baseline                          // no local edits
        let remote = makeWorkflow(model: "gpt-b")     // someone else changed it

        XCTAssertEqual(
            WorkflowSync.decide(remote: remote, local: local, baseline: baseline),
            .apply(remote)
        )
    }

    /// Our own save echoing back (server now equals local) advances the baseline
    /// and does NOT re-render — even if the stored baseline was stale.
    func testOwnEchoAdvancesBaseline() {
        let staleBaseline = makeWorkflow(model: "gpt-a")
        let local = makeWorkflow(model: "gpt-b")      // we edited then saved
        let remote = makeWorkflow(model: "gpt-b")     // server confirms our save

        XCTAssertEqual(
            WorkflowSync.decide(remote: remote, local: local, baseline: staleBaseline),
            .advanceBaseline(remote)
        )
    }

    /// Unsaved local edits (local drifted from the baseline) are never clobbered
    /// by a differing server copy.
    func testDirtyLocalEditsAreNotClobbered() {
        let baseline = makeWorkflow(model: "gpt-a")
        let local = makeWorkflow(model: "gpt-local")  // unsaved local edit
        let remote = makeWorkflow(model: "gpt-b")     // foreign edit races us

        XCTAssertEqual(
            WorkflowSync.decide(remote: remote, local: local, baseline: baseline),
            .skip
        )
    }

    /// With no baseline established, a divergent server copy is treated as unsafe
    /// (skip) rather than overwriting.
    func testNoBaselineDivergentSkips() {
        let local = makeWorkflow(model: "gpt-local")
        let remote = makeWorkflow(model: "gpt-b")

        XCTAssertEqual(
            WorkflowSync.decide(remote: remote, local: local, baseline: nil),
            .skip
        )
    }

    /// A change to a different workflow than the one open here is ignored.
    func testDifferentWorkflowIdSkips() {
        let baseline = makeWorkflow(id: "wf-1", model: "gpt-a")
        let local = baseline
        let remote = makeWorkflow(id: "wf-2", model: "gpt-b")

        XCTAssertEqual(
            WorkflowSync.decide(remote: remote, local: local, baseline: baseline),
            .skip
        )
    }
}
