import SwiftUI

// TODO: Refactor DynamicConfigView - extract field rendering into separate components
// Type body is 395 lines, target <350
/// Dynamically renders config form fields based on tool's config schema
// swiftlint:disable:next type_body_length
struct DynamicConfigView: View {
    let toolInfo: ToolInfo
    @Binding var config: [String: AnyCodableValue]?

    // State for each config value (keyed by config key)
    @State private var stringValues: [String: String] = [:]
    @State private var intValues: [String: Int] = [:]
    @State private var doubleValues: [String: Double] = [:]
    @State private var boolValues: [String: Bool] = [:]
    @State private var arrayValues: [String: [String]] = [:]
    @State private var showOutputSettings = false
    @State private var showAdvancedSettings = false

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            // Primary fields (always visible)
            ForEach(primaryKeys, id: \.self) { key in
                if let fieldSchema = getFieldSchema(for: key) {
                    configField(key: key, schema: fieldSchema)
                }
            }

            // Output settings (collapsed)
            if !outputKeys.isEmpty {
                DisclosureGroup("Output Settings", isExpanded: $showOutputSettings) {
                    VStack(alignment: .leading, spacing: 12) {
                        ForEach(outputKeys, id: \.self) { key in
                            if let fieldSchema = getFieldSchema(for: key) {
                                configField(key: key, schema: fieldSchema)
                            }
                        }
                    }
                    .padding(.top, 8)
                }
                .font(.caption)
            }

            // Advanced settings (collapsed)
            if !advancedKeys.isEmpty {
                DisclosureGroup("Advanced", isExpanded: $showAdvancedSettings) {
                    VStack(alignment: .leading, spacing: 12) {
                        ForEach(advancedKeys, id: \.self) { key in
                            if let fieldSchema = getFieldSchema(for: key) {
                                configField(key: key, schema: fieldSchema)
                            }
                        }
                    }
                    .padding(.top, 8)
                }
                .font(.caption)
            }
        }
        .onAppear {
            initializeValues()
        }
    }

    // MARK: - Grouped Keys

    /// Keys handled by dedicated UI sections (not rendered in DynamicConfigView)
    private let dedicatedKeys: Set<String> = ["provider_name", "model_name"]

    /// Visible keys filtered by x-hidden and dedicated sections
    private var visibleKeys: [String] {
        toolInfo.configSchema.keys.filter { key in
            guard !dedicatedKeys.contains(key) else { return false }
            guard let schema = getFieldSchema(for: key) else { return false }
            return !isHidden(schema: schema)
        }
    }

    /// Primary fields: x-group == "primary" or no x-group set (tool-specific fields)
    private var primaryKeys: [String] {
        let keys = visibleKeys.filter { key in
            guard let schema = getFieldSchema(for: key) else { return false }
            let group = getGroup(from: schema)
            return group == "primary" || group == nil
        }
        // Sort: key fields first, prompt last, others alphabetical
        let priorityOrder = ["collection_id", "vision_mode", "max_image_dimension"]
        let priority = keys.filter { priorityOrder.contains($0) }
            .sorted { priorityOrder.firstIndex(of: $0)! < priorityOrder.firstIndex(of: $1)! }
        let prompt = keys.filter { $0 == "prompt" }
        let others = keys.filter { !priorityOrder.contains($0) && $0 != "prompt" }.sorted()
        return priority + others + prompt
    }

    /// Output settings fields: x-group == "output"
    private var outputKeys: [String] {
        visibleKeys.filter { key in
            guard let schema = getFieldSchema(for: key) else { return false }
            return getGroup(from: schema) == "output"
        }.sorted()
    }

    /// Advanced fields: x-group == "advanced"
    private var advancedKeys: [String] {
        visibleKeys.filter { key in
            guard let schema = getFieldSchema(for: key) else { return false }
            return getGroup(from: schema) == "advanced"
        }.sorted()
    }

    // MARK: - Schema Helpers

    private func getFieldSchema(for key: String) -> [String: AnyCodableValue]? {
        guard case .dictionary(let schema) = toolInfo.configSchema[key] else {
            return nil
        }
        return schema
    }

    private func getType(from schema: [String: AnyCodableValue]) -> String? {
        if case .string(let type) = schema["type"] {
            return type
        }
        return nil
    }

    private func getDescription(from schema: [String: AnyCodableValue]) -> String? {
        if case .string(let desc) = schema["description"] {
            return desc
        }
        return nil
    }

    private func getDefault(from schema: [String: AnyCodableValue]) -> AnyCodableValue? {
        schema["default"]
    }

    private func getEnum(from schema: [String: AnyCodableValue]) -> [String]? {
        if case .array(let values) = schema["enum"] {
            return values.compactMap {
                if case .string(let str) = $0 {
                    return str
                }
                return nil
            }
        }
        return nil
    }

    private func isHidden(schema: [String: AnyCodableValue]) -> Bool {
        if case .bool(let hidden) = schema["x-hidden"] {
            return hidden
        }
        return false
    }

    private func getGroup(from schema: [String: AnyCodableValue]) -> String? {
        if case .string(let group) = schema["x-group"] {
            return group
        }
        return nil
    }

    private func getMin(from schema: [String: AnyCodableValue]) -> Double? {
        switch schema["min"] {
        case .double(let val): return val
        case .int(let val): return Double(val)
        default: return nil
        }
    }

    private func getMax(from schema: [String: AnyCodableValue]) -> Double? {
        switch schema["max"] {
        case .double(let val): return val
        case .int(let val): return Double(val)
        default: return nil
        }
    }

    // MARK: - Field Rendering

    @ViewBuilder
    private func configField(key: String, schema: [String: AnyCodableValue]) -> some View {
        if let type = getType(from: schema) {
            let description = getDescription(from: schema)
            let label = key.replacingOccurrences(of: "_", with: " ").capitalized

            VStack(alignment: .leading, spacing: 4) {
            Text(label)
                .font(.caption)
                .foregroundColor(.secondary)

            switch type {
            case "string":
                if let enumValues = getEnum(from: schema) {
                    enumPicker(key: key, label: label, options: enumValues, description: description)
                } else if key == "prompt" {
                    promptEditor(key: key, description: description)
                } else {
                    stringField(key: key, description: description)
                }

            case "integer":
                integerField(key: key, schema: schema, description: description)

            case "number":
                numberSlider(key: key, schema: schema, description: description)

            case "array":
                arrayField(key: key, schema: schema, description: description)

            case "boolean":
                // For booleans, description is used as toggle label - don't repeat below
                booleanToggle(key: key, description: description)

            default:
                Text("Unsupported type: \(type)")
                    .font(.caption2)
                    .foregroundColor(.red)
            }

                // Don't repeat description for booleans (it's already the toggle label)
                if type != "boolean", let desc = description {
                    Text(desc)
                        .font(.caption2)
                        .foregroundColor(.secondary)
                }
            }
        }
    }

    // MARK: - Field Types

    private func stringField(key: String, description: String?) -> some View {
        TextField(description ?? "Enter value", text: Binding(
            get: { stringValues[key] ?? "" },
            set: { newValue in
                stringValues[key] = newValue
                updateConfig(key: key, value: .string(newValue))
            }
        ))
        .textFieldStyle(.roundedBorder)
    }

    private func enumPicker(key: String, label: String, options: [String], description: String?) -> some View {
        Picker(label, selection: Binding(
            get: { stringValues[key] ?? options.first ?? "" },
            set: { newValue in
                stringValues[key] = newValue
                updateConfig(key: key, value: .string(newValue))
            }
        )) {
            ForEach(options, id: \.self) { option in
                Text(option).tag(option)
            }
        }
        .pickerStyle(.menu)
    }

    private func promptEditor(key: String, description: String?) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            ZStack(alignment: .topLeading) {
                // Placeholder showing default prompt
                if stringValues[key]?.isEmpty ?? true, let defaultPrompt = toolInfo.defaultPrompt {
                    Text(defaultPrompt)
                        .font(.caption)
                        .foregroundColor(.secondary.opacity(0.7))
                        .padding(.horizontal, 4)
                        .padding(.vertical, 8)
                }

                TextEditor(text: Binding(
                    get: { stringValues[key] ?? "" },
                    set: { newValue in
                        stringValues[key] = newValue
                        if newValue.isEmpty {
                            removeConfig(key: key)
                        } else {
                            updateConfig(key: key, value: .string(newValue))
                        }
                    }
                ))
                .font(.caption)
                .scrollContentBackground(.hidden)
                .background(Color.clear)
            }
            .frame(minHeight: 80)
            .background(Color(.textBackgroundColor))
            .overlay(
                RoundedRectangle(cornerRadius: 4)
                    .stroke(Color(.separatorColor), lineWidth: 1)
            )

            // Reset button (only when custom prompt is set)
            if !(stringValues[key]?.isEmpty ?? true) {
                Button(action: {
                    stringValues[key] = ""
                    removeConfig(key: key)
                }) {
                    Label("Reset to default", systemImage: "arrow.counterclockwise")
                        .font(.caption2)
                }
                .buttonStyle(.plain)
                .foregroundColor(.accentColor)
            }
        }
    }

    private func integerField(key: String, schema: [String: AnyCodableValue], description: String?) -> some View {
        Group {
            // Check if this is max_image_dimension - use preset picker
            if key == "max_image_dimension" {
                Picker("Max Image Size", selection: Binding(
                    get: { intValues[key] ?? 2048 },
                    set: { newValue in
                        intValues[key] = newValue
                        updateConfig(key: key, value: .int(newValue))
                    }
                )) {
                    Text("512px (Fastest)").tag(512)
                    Text("768px (Fast)").tag(768)
                    Text("1024px (Balanced)").tag(1024)
                    Text("1536px (Detailed)").tag(1536)
                    Text("2048px (Default)").tag(2048)
                    Text("Original Size (Maximum)").tag(0)
                }
                .pickerStyle(.menu)
            } else {
                // Generic integer field
                TextField("Enter number", value: Binding(
                    get: { intValues[key] ?? 0 },
                    set: { newValue in
                        intValues[key] = newValue
                        updateConfig(key: key, value: .int(newValue))
                    }
                ), formatter: NumberFormatter())
                .textFieldStyle(.roundedBorder)
            }
        }
    }

    private func booleanToggle(key: String, description: String?) -> some View {
        Toggle(description ?? "", isOn: Binding(
            get: { boolValues[key] ?? false },
            set: { newValue in
                boolValues[key] = newValue
                updateConfig(key: key, value: .bool(newValue))
            }
        ))
    }

    private func numberSlider(key: String, schema: [String: AnyCodableValue], description: String?) -> some View {
        let minVal = getMin(from: schema) ?? 0
        let maxVal = getMax(from: schema) ?? 1
        let step = maxVal <= 2 ? 0.1 : 1.0

        return HStack(spacing: 8) {
            Slider(
                value: Binding(
                    get: { doubleValues[key] ?? getDefaultDouble(from: schema) },
                    set: { newValue in
                        doubleValues[key] = newValue
                        updateConfig(key: key, value: .double(newValue))
                    }
                ),
                in: minVal...maxVal,
                step: step
            )
            Text(String(format: step < 1 ? "%.1f" : "%.0f", doubleValues[key] ?? getDefaultDouble(from: schema)))
                .font(.caption)
                .foregroundColor(.secondary)
                .frame(width: 30, alignment: .trailing)
        }
    }

    private func getDefaultDouble(from schema: [String: AnyCodableValue]) -> Double {
        switch schema["default"] {
        case .double(let val): return val
        case .int(let val): return Double(val)
        default: return 0
        }
    }

    private func arrayField(key: String, schema: [String: AnyCodableValue], description: String?) -> some View {
        // Render string arrays as semicolon-separated editable text
        let joined = (arrayValues[key] ?? getDefaultArray(from: schema)).joined(separator: "; ")

        return TextField(description ?? "Values (semicolon-separated)", text: Binding(
            get: { stringValues["\(key)_edit"] ?? joined },
            set: { newValue in
                stringValues["\(key)_edit"] = newValue
                let items = newValue
                    .split(separator: ";")
                    .map { $0.trimmingCharacters(in: .whitespaces) }
                    .filter { !$0.isEmpty }
                arrayValues[key] = items
                let arrayValue = AnyCodableValue.array(items.map { .string($0) })
                updateConfig(key: key, value: arrayValue)
            }
        ))
        .textFieldStyle(.roundedBorder)
        .font(.caption)
    }

    private func getDefaultArray(from schema: [String: AnyCodableValue]) -> [String] {
        if case .array(let values) = schema["default"] {
            return values.compactMap {
                if case .string(let str) = $0 { return str }
                return nil
            }
        }
        return []
    }

    // MARK: - State Management

    private func initializeValues() {
        // Initialize from existing config
        for (key, value) in config ?? [:] {
            switch value {
            case .string(let str):
                stringValues[key] = str
            case .int(let num):
                intValues[key] = num
            case .double(let num):
                doubleValues[key] = num
            case .bool(let flag):
                boolValues[key] = flag
            case .array(let items):
                let strings = items.compactMap { val -> String? in
                    if case .string(let stringValue) = val { return stringValue }
                    return nil
                }
                arrayValues[key] = strings
            default:
                break
            }
        }

        // Set defaults from schema if not in config
        for (key, schemaValue) in toolInfo.configSchema {
            guard case .dictionary(let schema) = schemaValue else { continue }

            // Skip if already set
            if config?[key] != nil { continue }

            if let defaultValue = getDefault(from: schema) {
                switch defaultValue {
                case .string(let str):
                    stringValues[key] = str
                case .int(let num):
                    intValues[key] = num
                case .double(let num):
                    doubleValues[key] = num
                case .bool(let flag):
                    boolValues[key] = flag
                case .array(let items):
                    let strings = items.compactMap { val -> String? in
                        if case .string(let stringValue) = val { return stringValue }
                        return nil
                    }
                    arrayValues[key] = strings
                default:
                    break
                }
            }
        }
    }

    private func updateConfig(key: String, value: AnyCodableValue) {
        if config == nil {
            config = [:]
        }
        config?[key] = value
    }

    private func removeConfig(key: String) {
        config?.removeValue(forKey: key)
    }
}
