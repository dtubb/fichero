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

    // MARK: - Opening a node config never writes config (F4-residual)

    /// spec: workflow-node-config nodeconfig.roundtrip.open-is-read-only — the transcribe config
    /// normalises a legacy language code on open (es → es-ES); that seed must NOT trip the pickers'
    /// config-writing onChange, or merely OPENING the node autosaves it. The load guards those writes.
    func testTranscribeConfigLoadDoesNotWriteConfig() throws {
        let url = try AppSource.root()
            .appendingPathComponent("Views/Workflow/Nodes/NodeConfigs/TranscribeNodeConfig.swift")
        let source = try String(contentsOf: url, encoding: .utf8)
        // The load raises the guard...
        XCTAssertTrue(source.contains("isLoadingConfig = true"),
                      "loadInitialState must mark the load so onChange writes are suppressed")
        // ...and the config-writing onChange handlers check it (both language + max-image writes).
        let guardCount = source.components(separatedBy: "guard !isLoadingConfig else { return }").count - 1
        XCTAssertGreaterThanOrEqual(guardCount, 2,
                                    "both config-writing onChange handlers must guard on the load flag")
    }

    /// spec: workflow-node-config nodeconfig.roundtrip.open-is-read-only — the Search node seeds
    /// `selectedSearchId` from config on open, and its onChange rewrites `search_id`/`query`; that
    /// seed must not autosave merely because the node was opened.
    func testSearchConfigLoadDoesNotWriteConfig() throws {
        let url = try AppSource.root()
            .appendingPathComponent("Views/Workflow/Nodes/NodeConfigs/SearchNodeConfig.swift")
        let source = try String(contentsOf: url, encoding: .utf8)
        XCTAssertTrue(source.contains("isLoadingConfig = true"),
                      "loadInitialState must mark the load so the search_id/query onChange is suppressed")
        XCTAssertTrue(source.contains("guard !isLoadingConfig else { return }"),
                      "the search-id onChange must guard on the load flag")
    }
}
