import Foundation

// MARK: - Supporting Types

struct CategoryTools: Codable, Identifiable {
    let category: String
    let displayName: String
    let tools: [ToolInfo]

    var id: String { category }

    enum CodingKeys: String, CodingKey {
        case category, tools
        case displayName = "display_name"
    }
}

struct ToolInfo: Codable, Identifiable {
    let name: String
    let displayName: String
    let description: String
    let category: String
    let icon: String
    let color: String
    let inputPorts: [PortInfo]
    let outputPorts: [PortInfo]
    let configSchema: [String: AnyCodableValue]
    let configDefaults: [String: AnyCodableValue]  // Default config values for new nodes
    let defaultOutputSchema: [String: AnyCodableValue]?  // Default structured output schema
    let defaultPrompt: String?  // Default prompt for LLM tools (from backend)
    let usesLLM: Bool
    let supportsBatch: Bool
    let supportsStreaming: Bool
    let supportsStructuredOutput: Bool
    let sortOrder: Int
    let tested: Bool  // false = UNTESTED; only the HTR chain is tested today
    /// A HARD requirement, not a preference (#4345): the tool parses the
    /// model's answer, so a recognition-only model (Apple Vision OCR returns
    /// page text and ignores the prompt) can never satisfy it. Preflight
    /// refuses such a node before the run starts.
    let requiresGenerativeModel: Bool

    var id: String { name }

    enum CodingKeys: String, CodingKey {
        case name, description, category, icon, color, tested
        case displayName = "display_name"
        case inputPorts = "input_ports"
        case outputPorts = "output_ports"
        case configSchema = "config_schema"
        case configDefaults = "config_defaults"
        case defaultOutputSchema = "default_output_schema"
        case defaultPrompt = "default_prompt"
        case usesLLM = "uses_llm"
        case supportsBatch = "supports_batch"
        case supportsStreaming = "supports_streaming"
        case supportsStructuredOutput = "supports_structured_output"
        case sortOrder = "sort_order"
        case requiresGenerativeModel = "requires_generative_model"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        name = try container.decode(String.self, forKey: .name)
        displayName = try container.decode(String.self, forKey: .displayName)
        description = try container.decode(String.self, forKey: .description)
        category = try container.decode(String.self, forKey: .category)
        icon = try container.decode(String.self, forKey: .icon)
        color = try container.decode(String.self, forKey: .color)
        inputPorts = try container.decode([PortInfo].self, forKey: .inputPorts)
        outputPorts = try container.decode([PortInfo].self, forKey: .outputPorts)
        configSchema = try container.decodeIfPresent([String: AnyCodableValue].self, forKey: .configSchema) ?? [:]
        configDefaults = try container.decodeIfPresent([String: AnyCodableValue].self, forKey: .configDefaults) ?? [:]
        defaultOutputSchema = try container.decodeIfPresent([String: AnyCodableValue].self, forKey: .defaultOutputSchema)
        defaultPrompt = try container.decodeIfPresent(String.self, forKey: .defaultPrompt)
        usesLLM = try container.decode(Bool.self, forKey: .usesLLM)
        supportsBatch = try container.decode(Bool.self, forKey: .supportsBatch)
        supportsStreaming = try container.decode(Bool.self, forKey: .supportsStreaming)
        supportsStructuredOutput = try container.decode(Bool.self, forKey: .supportsStructuredOutput)
        sortOrder = try container.decode(Int.self, forKey: .sortOrder)
        // Default to UNTESTED when the backend omits the field (older engines).
        tested = try container.decodeIfPresent(Bool.self, forKey: .tested) ?? false
        requiresGenerativeModel = try container.decodeIfPresent(
            Bool.self, forKey: .requiresGenerativeModel) ?? false
    }

    /// Memberwise initializer for creating ToolInfo from code
    init(
        name: String,
        displayName: String,
        description: String,
        category: String,
        icon: String,
        color: String,
        inputPorts: [PortInfo],
        outputPorts: [PortInfo],
        configSchema: [String: AnyCodableValue] = [:],
        configDefaults: [String: AnyCodableValue] = [:],
        defaultOutputSchema: [String: AnyCodableValue]? = nil,
        defaultPrompt: String? = nil,
        usesLLM: Bool,
        supportsBatch: Bool,
        supportsStreaming: Bool,
        supportsStructuredOutput: Bool,
        sortOrder: Int,
        tested: Bool = false,
        requiresGenerativeModel: Bool = false
    ) {
        self.name = name
        self.displayName = displayName
        self.description = description
        self.category = category
        self.icon = icon
        self.color = color
        self.inputPorts = inputPorts
        self.outputPorts = outputPorts
        self.configSchema = configSchema
        self.configDefaults = configDefaults
        self.defaultOutputSchema = defaultOutputSchema
        self.defaultPrompt = defaultPrompt
        self.usesLLM = usesLLM
        self.requiresGenerativeModel = requiresGenerativeModel
        self.supportsBatch = supportsBatch
        self.supportsStreaming = supportsStreaming
        self.supportsStructuredOutput = supportsStructuredOutput
        self.sortOrder = sortOrder
        self.tested = tested
    }
}

/// Codable wrapper for Any values in config schemas
enum AnyCodableValue: Codable, Hashable {
    case string(String)
    case int(Int)
    case double(Double)
    case bool(Bool)
    case array([AnyCodableValue])
    case dictionary([String: AnyCodableValue])
    case null

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if let string = try? container.decode(String.self) {
            self = .string(string)
        } else if let int = try? container.decode(Int.self) {
            self = .int(int)
        } else if let double = try? container.decode(Double.self) {
            self = .double(double)
        } else if let bool = try? container.decode(Bool.self) {
            self = .bool(bool)
        } else if let array = try? container.decode([AnyCodableValue].self) {
            self = .array(array)
        } else if let dict = try? container.decode([String: AnyCodableValue].self) {
            self = .dictionary(dict)
        } else if container.decodeNil() {
            self = .null
        } else {
            throw DecodingError.typeMismatch(
                AnyCodableValue.self,
                DecodingError.Context(codingPath: decoder.codingPath, debugDescription: "Unsupported type")
            )
        }
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .string(let value):
            try container.encode(value)
        case .int(let value):
            try container.encode(value)
        case .double(let value):
            try container.encode(value)
        case .bool(let value):
            try container.encode(value)
        case .array(let value):
            try container.encode(value)
        case .dictionary(let value):
            try container.encode(value)
        case .null:
            try container.encodeNil()
        }
    }
}

struct PortInfo: Codable, Identifiable, Hashable {
    let id: String
    let name: String
    let portType: String  // "input" or "output"
    let dataType: String
    let required: Bool
    let description: String
    let defaultValue: AnyCodableValue?  // Default value for optional inputs

    enum CodingKeys: String, CodingKey {
        case id, name, description, required
        case portType = "port_type"
        case dataType = "data_type"
        case defaultValue = "default"
    }

    init(
        id: String,
        name: String,
        portType: String,
        dataType: String,
        required: Bool = true,
        description: String = "",
        defaultValue: AnyCodableValue? = nil
    ) {
        self.id = id
        self.name = name
        self.portType = portType
        self.dataType = dataType
        self.required = required
        self.description = description
        self.defaultValue = defaultValue
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decode(String.self, forKey: .id)
        name = try container.decode(String.self, forKey: .name)
        portType = try container.decode(String.self, forKey: .portType)
        dataType = try container.decode(String.self, forKey: .dataType)
        required = try container.decodeIfPresent(Bool.self, forKey: .required) ?? true
        description = try container.decodeIfPresent(String.self, forKey: .description) ?? ""
        defaultValue = try container.decodeIfPresent(AnyCodableValue.self, forKey: .defaultValue)
    }

    /// Whether this is an input port
    var isInput: Bool { portType == "input" }

    /// Whether this is an output port
    var isOutput: Bool { portType == "output" }
}
