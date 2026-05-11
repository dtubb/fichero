@testable import Fichero
import XCTest

/// Tests for WorkflowChain Codable surface — multi-workflow execution
/// graph + step results. Locks every snake_case key the backend sends
/// (this is the source of every chain-execution-not-rendering bug).
final class WorkflowChainTests: XCTestCase {

    // MARK: - WorkflowChain defaults

    func testWorkflowChainInitDefaults() {
        let chain = WorkflowChain(name: "Test")
        XCTAssertFalse(chain.id.isEmpty)  // UUID default
        XCTAssertEqual(chain.description, "")
        XCTAssertTrue(chain.steps.isEmpty)
        XCTAssertNil(chain.entryStep)
        XCTAssertTrue(chain.initialInputs.isEmpty)
        XCTAssertEqual(chain.folderPath, "/")
        XCTAssertEqual(chain.sortOrder, 0)
    }

    func testChainStepInitDefaults() {
        let step = ChainStep(workflowId: "wf-1")
        XCTAssertFalse(step.id.isEmpty)
        XCTAssertEqual(step.name, "")
        XCTAssertTrue(step.inputMappings.isEmpty)
        XCTAssertTrue(step.staticInputs.isEmpty)
        XCTAssertNil(step.condition)
        XCTAssertFalse(step.continueOnError)
        XCTAssertEqual(step.timeoutSeconds, 300)
    }

    func testOutputMappingDefaults() {
        let mapping = OutputMapping(sourcePath: "a", targetKey: "b")
        XCTAssertNil(mapping.transform)
    }

    func testChainStepConditionDefaults() {
        let cond = ChainStepCondition(expression: "x > 0")
        XCTAssertNil(cond.trueStep)
        XCTAssertNil(cond.falseStep)
    }

    // MARK: - Snake_case decode

    func testWorkflowChainDecodesSnakeCase() throws {
        let json = """
        {
            "id": "c-1", "name": "Chain", "description": "",
            "steps": [], "entry_step": "s1", "initial_inputs": {},
            "created_at": "2026-05-10T10:00:00Z",
            "updated_at": "2026-05-10T10:00:00Z",
            "folder_path": "/Chains", "sort_order": 3
        }
        """.data(using: .utf8)!
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        let chain = try decoder.decode(WorkflowChain.self, from: json)
        XCTAssertEqual(chain.entryStep, "s1")
        XCTAssertEqual(chain.folderPath, "/Chains")
        XCTAssertEqual(chain.sortOrder, 3)
    }

    func testChainStepDecodesSnakeCase() throws {
        let json = """
        {
            "id": "s1", "workflow_id": "wf-1", "name": "step one",
            "input_mappings": [
                {"source_path": "out.text", "target_key": "input", "transform": null}
            ],
            "static_inputs": {},
            "condition": null,
            "continue_on_error": true,
            "timeout_seconds": 60
        }
        """.data(using: .utf8)!
        let step = try JSONDecoder().decode(ChainStep.self, from: json)
        XCTAssertEqual(step.workflowId, "wf-1")
        XCTAssertTrue(step.continueOnError)
        XCTAssertEqual(step.timeoutSeconds, 60)
        XCTAssertEqual(step.inputMappings.count, 1)
        XCTAssertEqual(step.inputMappings.first?.sourcePath, "out.text")
        XCTAssertEqual(step.inputMappings.first?.targetKey, "input")
    }

    func testChainStepConditionDecodesSnakeCase() throws {
        let json = """
        {
            "expression": "x > 0",
            "true_step": "step-a",
            "false_step": "step-b"
        }
        """.data(using: .utf8)!
        let cond = try JSONDecoder().decode(ChainStepCondition.self, from: json)
        XCTAssertEqual(cond.expression, "x > 0")
        XCTAssertEqual(cond.trueStep, "step-a")
        XCTAssertEqual(cond.falseStep, "step-b")
    }

    // MARK: - ChainStepStatus

    func testChainStepStatusRawValuesStable() {
        // Source-of-truth strings come from the Python backend.
        XCTAssertEqual(ChainStepStatus.pending.rawValue, "pending")
        XCTAssertEqual(ChainStepStatus.running.rawValue, "running")
        XCTAssertEqual(ChainStepStatus.completed.rawValue, "completed")
        XCTAssertEqual(ChainStepStatus.skipped.rawValue, "skipped")
        XCTAssertEqual(ChainStepStatus.failed.rawValue, "failed")
        XCTAssertEqual(ChainStepStatus.cancelled.rawValue, "cancelled")
    }

    func testChainStepStatusDecodes() throws {
        let data = "\"running\"".data(using: .utf8)!
        XCTAssertEqual(try JSONDecoder().decode(ChainStepStatus.self, from: data), .running)
    }

    // MARK: - ChainStepResult + ChainExecutionResult ids

    func testChainStepResultIdIsStepId() throws {
        let json = """
        {
            "step_id": "s1", "workflow_id": "wf-1",
            "status": "completed",
            "inputs": {}, "outputs": {},
            "output_files": ["/tmp/a.pdf"],
            "error": null,
            "duration_ms": 1500.0
        }
        """.data(using: .utf8)!
        let result = try JSONDecoder().decode(ChainStepResult.self, from: json)
        XCTAssertEqual(result.id, "s1")
        XCTAssertEqual(result.workflowId, "wf-1")
        XCTAssertEqual(result.status, .completed)
        XCTAssertEqual(result.outputFiles, ["/tmp/a.pdf"])
        XCTAssertEqual(result.durationMs, 1500.0)
    }

    func testChainExecutionResultIdIsExecutionId() throws {
        let json = """
        {
            "chain_id": "c-1", "execution_id": "e-1",
            "status": "completed",
            "step_results": [],
            "final_outputs": {},
            "final_files": [],
            "total_duration_ms": 5000.0
        }
        """.data(using: .utf8)!
        let result = try JSONDecoder().decode(ChainExecutionResult.self, from: json)
        XCTAssertEqual(result.id, "e-1")
        XCTAssertEqual(result.chainId, "c-1")
        XCTAssertEqual(result.totalDurationMs, 5000.0)
    }

    // MARK: - ChainProgressEvent

    func testChainProgressEventDecodes() throws {
        let json = """
        {
            "event_type": "step_start",
            "step_id": "s1",
            "message": "Running",
            "progress": 0.25,
            "timestamp": "2026-05-10T10:00:00Z"
        }
        """.data(using: .utf8)!
        let ev = try JSONDecoder().decode(ChainProgressEvent.self, from: json)
        XCTAssertEqual(ev.eventType, "step_start")
        XCTAssertEqual(ev.stepId, "s1")
        XCTAssertEqual(ev.progress, 0.25)
    }

    func testChainProgressEventOptionalStepId() throws {
        // Chain-level events (e.g. chain_start) have no step_id.
        let json = """
        {
            "event_type": "chain_complete",
            "step_id": null,
            "message": "Done",
            "progress": 1.0,
            "timestamp": "2026-05-10T10:00:00Z"
        }
        """.data(using: .utf8)!
        let ev = try JSONDecoder().decode(ChainProgressEvent.self, from: json)
        XCTAssertNil(ev.stepId)
    }

    // MARK: - Request/Response shapes

    func testCreateChainRequestEncodesSnakeCase() throws {
        let req = CreateChainRequest(
            name: "Test", description: "",
            steps: [], entryStep: "s1", initialInputs: [:]
        )
        let data = try JSONEncoder().encode(req)
        let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        XCTAssertEqual(json?["entry_step"] as? String, "s1")
        XCTAssertNotNil(json?["initial_inputs"])
    }

    func testExecuteChainRequestEncodesSnakeCase() throws {
        let req = ExecuteChainRequest(inputs: [:], inputFiles: ["/tmp/a.pdf"])
        let data = try JSONEncoder().encode(req)
        let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        XCTAssertEqual(json?["input_files"] as? [String], ["/tmp/a.pdf"])
    }

    func testExecuteChainResponseDecodesSnakeCase() throws {
        let json = """
        {
            "execution_id": "e-1",
            "chain_id": "c-1",
            "status": "pending",
            "message": "Queued"
        }
        """.data(using: .utf8)!
        let resp = try JSONDecoder().decode(ExecuteChainResponse.self, from: json)
        XCTAssertEqual(resp.executionId, "e-1")
        XCTAssertEqual(resp.chainId, "c-1")
        XCTAssertEqual(resp.message, "Queued")
    }

    func testChainListResponseDecodes() throws {
        let json = """
        {"chains": [], "total": 0}
        """.data(using: .utf8)!
        let resp = try JSONDecoder().decode(ChainListResponse.self, from: json)
        XCTAssertEqual(resp.total, 0)
        XCTAssertTrue(resp.chains.isEmpty)
    }

    func testChainExecutionStatusResponseDecodes() throws {
        let json = """
        {
            "execution_id": "e-1",
            "chain_id": "c-1",
            "status": "running",
            "step_results": [],
            "final_outputs": {},
            "final_files": [],
            "total_duration_ms": 0.0,
            "events": []
        }
        """.data(using: .utf8)!
        let resp = try JSONDecoder().decode(ChainExecutionStatusResponse.self, from: json)
        XCTAssertEqual(resp.executionId, "e-1")
        XCTAssertEqual(resp.status, "running")
    }
}
