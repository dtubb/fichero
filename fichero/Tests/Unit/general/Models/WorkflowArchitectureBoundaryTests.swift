import XCTest

final class WorkflowArchitectureBoundaryTests: XCTestCase {
    func testWorkflowChainViewsReadFromChainStore() throws {
        let chainEditorSource = try Self.appSource("Views/Workflow/Editor/ChainEditorView.swift")
        XCTAssertTrue(chainEditorSource.contains("@Environment(ChainStore.self) var chainStore"))
        XCTAssertFalse(chainEditorSource.contains("ChainService(apiClient:"))
    }

    func testWorkflowEditorWaitsOnContinuationInsteadOfPollingLoop() throws {
        let source = try Self.appSource("Views/Workflow/Editor/WorkflowEditor+Actions.swift")
        XCTAssertTrue(source.contains("let completion = WorkflowRunCompletion()"))
        XCTAssertTrue(source.contains("await completion.wait()"))
        XCTAssertFalse(source.contains("while !streamCompleted"))
    }

    private static func appSource(_ relativePath: String) throws -> String {
        let baseURL = try AppSource.root()
        return try String(contentsOf: baseURL.appendingPathComponent(relativePath), encoding: .utf8)
    }
}
