@testable import Fichero
import XCTest

/// #4514: a LOCKED system preset (Default Workflows) selected in the editor
/// was auto-saved anyway; the server 403'd the PUT and the client surfaced it
/// as "Auto-save failed: Unexpected response from server" ×N. Two seams pin
/// the fix:
///  - `WorkflowSavePolicy.canAutoSave` — the editor must not fire a save for
///    a read-only workflow at all (it knows the flag);
///  - `WorkflowServiceError.readOnlyWorkflow` — any 403 that does surface is
///    typed and worded, never "Unexpected response".
final class WorkflowReadOnlySavePolicyTests: XCTestCase {

    // MARK: - WorkflowSavePolicy

    func testUserWorkflowMayAutoSave() {
        XCTAssertTrue(WorkflowSavePolicy.canAutoSave(editorIsSystem: false, canonicalIsSystem: false))
    }

    func testUserWorkflowWithNoCanonicalRowMayAutoSave() {
        XCTAssertTrue(WorkflowSavePolicy.canAutoSave(editorIsSystem: false, canonicalIsSystem: nil))
    }

    func testSystemFlagOnEditorCopyBlocksAutoSave() {
        XCTAssertFalse(WorkflowSavePolicy.canAutoSave(editorIsSystem: true, canonicalIsSystem: true))
        XCTAssertFalse(WorkflowSavePolicy.canAutoSave(editorIsSystem: true, canonicalIsSystem: nil))
    }

    func testSystemFlagOnCanonicalRowBlocksAutoSaveEvenIfEditorCopyLostIt() {
        // A stale editor snapshot without the flag must not sneak a doomed
        // PUT through — the sidebar row is authoritative.
        XCTAssertFalse(WorkflowSavePolicy.canAutoSave(editorIsSystem: false, canonicalIsSystem: true))
    }

    // MARK: - Typed refusal wording

    func testReadOnlyRefusalIsTypedAndWorded() {
        let error = WorkflowServiceError.readOnlyWorkflow
        XCTAssertEqual(
            error.localizedDescription,
            "This is a built-in workflow and can't be edited — duplicate it to customize."
        )
        XCTAssertNotEqual(
            error.localizedDescription,
            WorkflowServiceError.unexpectedResponse.localizedDescription,
            "a read-only refusal must never read as an unexpected response"
        )
    }
}
