import Foundation

// MARK: - Workflow Chain Models

/// A workflow chain connects multiple workflows together
struct WorkflowChain: Identifiable, Codable, Equatable, Hashable {
    let id: String
    var name: String
    var description: String
    var steps: [ChainStep]
    var entryStep: String?
    var initialInputs: [String: AnyCodableValue]
    var createdAt: Date
    var updatedAt: Date
    var folderPath: String
    var sortOrder: Int

    init(
        id: String = UUID().uuidString,
        name: String,
        description: String = "",
        steps: [ChainStep] = [],
        entryStep: String? = nil,
        initialInputs: [String: AnyCodableValue] = [:],
        createdAt: Date = Date(),
        updatedAt: Date = Date(),
        folderPath: String = "/",
        sortOrder: Int = 0
    ) {
        self.id = id
        self.name = name
        self.description = description
        self.steps = steps
        self.entryStep = entryStep
        self.initialInputs = initialInputs
        self.createdAt = createdAt
        self.updatedAt = updatedAt
        self.folderPath = folderPath
        self.sortOrder = sortOrder
    }

    enum CodingKeys: String, CodingKey {
        case id, name, description, steps
        case entryStep = "entry_step"
        case initialInputs = "initial_inputs"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
        case folderPath = "folder_path"
        case sortOrder = "sort_order"
    }
}

/// A single step in a workflow chain
struct ChainStep: Identifiable, Codable, Equatable, Hashable {
    let id: String
    var workflowId: String
    var name: String
    var inputMappings: [OutputMapping]
    var staticInputs: [String: AnyCodableValue]
    var condition: ChainStepCondition?
    var continueOnError: Bool
    var timeoutSeconds: Int

    init(
        id: String = UUID().uuidString,
        workflowId: String,
        name: String = "",
        inputMappings: [OutputMapping] = [],
        staticInputs: [String: AnyCodableValue] = [:],
        condition: ChainStepCondition? = nil,
        continueOnError: Bool = false,
        timeoutSeconds: Int = 300
    ) {
        self.id = id
        self.workflowId = workflowId
        self.name = name
        self.inputMappings = inputMappings
        self.staticInputs = staticInputs
        self.condition = condition
        self.continueOnError = continueOnError
        self.timeoutSeconds = timeoutSeconds
    }

    enum CodingKeys: String, CodingKey {
        case id, name, condition
        case workflowId = "workflow_id"
        case inputMappings = "input_mappings"
        case staticInputs = "static_inputs"
        case continueOnError = "continue_on_error"
        case timeoutSeconds = "timeout_seconds"
    }
}

/// Maps output from one workflow to input of the next
struct OutputMapping: Codable, Equatable, Hashable {
    var sourcePath: String
    var targetKey: String
    var transform: String?

    init(sourcePath: String, targetKey: String, transform: String? = nil) {
        self.sourcePath = sourcePath
        self.targetKey = targetKey
        self.transform = transform
    }

    enum CodingKeys: String, CodingKey {
        case sourcePath = "source_path"
        case targetKey = "target_key"
        case transform
    }
}

/// Condition for executing a chain step
struct ChainStepCondition: Codable, Equatable, Hashable {
    var expression: String
    var trueStep: String?
    var falseStep: String?

    init(expression: String, trueStep: String? = nil, falseStep: String? = nil) {
        self.expression = expression
        self.trueStep = trueStep
        self.falseStep = falseStep
    }

    enum CodingKeys: String, CodingKey {
        case expression
        case trueStep = "true_step"
        case falseStep = "false_step"
    }
}

// MARK: - Chain Execution Models

/// Status of a chain step execution
enum ChainStepStatus: String, Codable {
    case pending
    case running
    case completed
    case skipped
    case failed
    case cancelled
}

/// Result of executing a single chain step
struct ChainStepResult: Identifiable, Codable {
    var id: String { stepId }
    let stepId: String
    let workflowId: String
    let status: ChainStepStatus
    let inputs: [String: AnyCodableValue]
    let outputs: [String: AnyCodableValue]
    let outputFiles: [String]
    let error: String?
    let durationMs: Double

    enum CodingKeys: String, CodingKey {
        case stepId = "step_id"
        case workflowId = "workflow_id"
        case status, inputs, outputs, error
        case outputFiles = "output_files"
        case durationMs = "duration_ms"
    }
}

/// Result of executing a complete chain
struct ChainExecutionResult: Identifiable, Codable {
    var id: String { executionId }
    let chainId: String
    let executionId: String
    let status: ChainStepStatus
    let stepResults: [ChainStepResult]
    let finalOutputs: [String: AnyCodableValue]
    let finalFiles: [String]
    let totalDurationMs: Double

    enum CodingKeys: String, CodingKey {
        case chainId = "chain_id"
        case executionId = "execution_id"
        case status
        case stepResults = "step_results"
        case finalOutputs = "final_outputs"
        case finalFiles = "final_files"
        case totalDurationMs = "total_duration_ms"
    }
}

/// Progress event for chain execution
struct ChainProgressEvent: Codable {
    let eventType: String
    let stepId: String?
    let message: String
    let progress: Double
    let timestamp: String

    enum CodingKeys: String, CodingKey {
        case eventType = "event_type"
        case stepId = "step_id"
        case message, progress, timestamp
    }
}

/// Response from chain execution status endpoint
struct ChainExecutionStatusResponse: Codable {
    let executionId: String
    let chainId: String
    let status: String
    let stepResults: [ChainStepResult]
    let finalOutputs: [String: AnyCodableValue]
    let finalFiles: [String]
    let totalDurationMs: Double
    let events: [ChainProgressEvent]

    enum CodingKeys: String, CodingKey {
        case executionId = "execution_id"
        case chainId = "chain_id"
        case status
        case stepResults = "step_results"
        case finalOutputs = "final_outputs"
        case finalFiles = "final_files"
        case totalDurationMs = "total_duration_ms"
        case events
    }
}

// MARK: - API Request/Response Models

/// Request to create a new chain
struct CreateChainRequest: Codable {
    let name: String
    let description: String
    let steps: [ChainStep]
    let entryStep: String?
    let initialInputs: [String: AnyCodableValue]

    enum CodingKeys: String, CodingKey {
        case name, description, steps
        case entryStep = "entry_step"
        case initialInputs = "initial_inputs"
    }
}

/// Request to execute a chain
struct ExecuteChainRequest: Codable {
    let inputs: [String: AnyCodableValue]
    let inputFiles: [String]

    enum CodingKeys: String, CodingKey {
        case inputs
        case inputFiles = "input_files"
    }
}

/// Response from execute chain endpoint
struct ExecuteChainResponse: Codable {
    let executionId: String
    let chainId: String
    let status: String
    let message: String

    enum CodingKeys: String, CodingKey {
        case executionId = "execution_id"
        case chainId = "chain_id"
        case status, message
    }
}

/// Response from list chains endpoint
struct ChainListResponse: Codable {
    let chains: [WorkflowChain]
    let total: Int
}
