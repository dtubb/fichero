@testable import Fichero
import Foundation
import Testing

/// #4523 / #4396 ask #3: a run that would WIDEN beyond the user's selection
/// must ask before dispatching.
///
/// `WorkflowRunScope.Resolution.widensBeyondSelection` was introduced by the
/// #4396 fix so callers could ask first — and then nothing consulted it: its
/// only reader in the whole app was a log line. With every shipped preset
/// decoding `input_source` to the `.collection` default, and the editor's
/// selection (`browserSelection`) cleared by ordinary sidebar navigation,
/// pressing Run with one TIF "selected" silently ran the entire folder,
/// billing per page across documents the user never chose.
///
/// These tests pin the gate itself (`runNeedsWideningConfirmation`, pure, over
/// every `WorkflowRunScope.resolve` outcome) and — because the gate is view
/// glue a unit test cannot click — structurally pin that `runWorkflow()`
/// consults it before dispatch and that the dispatched run uses the CONFIRMED
/// scope rather than re-resolving. Both structural pins fail against the
/// pre-fix source (no gate call existed; `performWorkflowRun` re-resolved),
/// so they are proven to fire, not merely to pass.
struct WorkflowEditorRunGateTests {

    // MARK: - The gate, over real resolver outcomes

    @Test("a run honouring any selection never needs confirmation")
    func selectionNeverConfirms() {
        for inputSource in [WorkflowInputSource.collection, .currentSelection] {
            let scope = WorkflowRunScope.resolve(
                inputSource: inputSource,
                selection: ["doc-1"],
                collectionId: "folder-1",
                fallbackDocumentId: nil
            )
            #expect(!WorkflowEditor.runNeedsWideningConfirmation(scope))
        }
    }

    @Test("an empty selection on a collection workflow — the #4523 case — must confirm")
    func emptySelectionOnCollectionWorkflowConfirms() {
        // Every shipped preset omits input_source, and the decoder defaults it
        // to .collection — this is the NORMAL case, not an edge.
        let scope = WorkflowRunScope.resolve(
            inputSource: .collection,
            selection: [],
            collectionId: "folder-1",
            fallbackDocumentId: nil
        )
        #expect(scope.widensBeyondSelection)
        #expect(WorkflowEditor.runNeedsWideningConfirmation(scope))
    }

    @Test("the single-document fallback does not confirm — it is not a widening")
    func fallbackDocumentDoesNotConfirm() {
        let scope = WorkflowRunScope.resolve(
            inputSource: .currentSelection,
            selection: [],
            collectionId: nil,
            fallbackDocumentId: "doc-1"
        )
        #expect(!WorkflowEditor.runNeedsWideningConfirmation(scope))
    }

    @Test("an empty resolution does not confirm — there is nothing to run on")
    func emptyResolutionDoesNotConfirm() {
        let scope = WorkflowRunScope.resolve(
            inputSource: .currentSelection,
            selection: [],
            collectionId: nil,
            fallbackDocumentId: nil
        )
        #expect(scope.docIds.isEmpty)
        #expect(!WorkflowEditor.runNeedsWideningConfirmation(scope))
    }

    @Test("the gate answers exactly widensBeyondSelection — no second predicate to drift")
    func gateMirrorsTheResolutionFlag() {
        let widening = WorkflowRunScope.resolve(
            inputSource: .collection, selection: [], collectionId: "f", fallbackDocumentId: nil
        )
        let honoured = WorkflowRunScope.resolve(
            inputSource: .collection, selection: ["d"], collectionId: "f", fallbackDocumentId: nil
        )
        #expect(WorkflowEditor.runNeedsWideningConfirmation(widening) == widening.widensBeyondSelection)
        #expect(WorkflowEditor.runNeedsWideningConfirmation(honoured) == honoured.widensBeyondSelection)
    }

    // MARK: - Structural pins on the view glue

    private func actionsSource() throws -> String {
        let root = URL(fileURLWithPath: #filePath)      // …/fichero-tests/Views/Workflow/…
            .deletingLastPathComponent()                // Workflow
            .deletingLastPathComponent()                // Views
            .deletingLastPathComponent()                // fichero-tests
            .deletingLastPathComponent()                // fichero (package root)
        let file = root
            .appendingPathComponent("fichero/Views/Workflow/Editor/WorkflowEditor+Actions.swift")
        return try String(contentsOf: file, encoding: .utf8)
    }

    /// Fails on pre-fix source: `runWorkflow()` had no gate call at all.
    @Test("runWorkflow() consults the gate before any dispatch")
    func runWorkflowConsultsTheGate() throws {
        let source = try actionsSource()
        guard let runBody = source.range(of: "func runWorkflow()") else {
            Issue.record("runWorkflow() not found")
            return
        }
        let afterRun = source[runBody.upperBound...]
        let gateCall = afterRun.range(of: "runNeedsWideningConfirmation")
        let dispatch = afterRun.range(of: "dispatchRun(")
        #expect(gateCall != nil, "runWorkflow() must consult runNeedsWideningConfirmation")
        if let gateCall, let dispatch {
            #expect(
                gateCall.lowerBound < dispatch.lowerBound,
                "the gate must be consulted BEFORE dispatch"
            )
        }
    }

    /// Fails on pre-fix source: `performWorkflowRun` re-resolved the scope
    /// internally, so a confirmed scope could be silently replaced.
    @Test("the dispatched run uses the confirmed scope — no re-resolution inside performWorkflowRun")
    func dispatchedRunUsesTheConfirmedScope() throws {
        let source = try actionsSource()
        guard let performStart = source.range(of: "private func performWorkflowRun(") else {
            Issue.record("performWorkflowRun not found")
            return
        }
        let body = source[performStart.upperBound...]
        // The resolver may exist elsewhere in the file (runWorkflow calls it);
        // it must not be called from inside performWorkflowRun's body, which
        // ends where the next top-level helper begins.
        let bodyEnd = body.range(of: "\n    private func ")?.lowerBound
            ?? body.range(of: "\n    func ")?.lowerBound
            ?? body.endIndex
        let performBody = body[..<bodyEnd]
        #expect(
            !performBody.contains("resolveRunScope()"),
            "performWorkflowRun must run the scope it was handed, not re-resolve"
        )
        #expect(performStart.upperBound < source.endIndex)
    }
}
