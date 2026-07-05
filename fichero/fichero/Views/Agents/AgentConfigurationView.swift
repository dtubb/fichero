import FicheroAPIClient
import OSLog
import SwiftUI

private let logger = Logger(subsystem: "app.fichero.fichero", category: "AgentConfigurationView")

/// View for configuring an agent node in a workflow
struct AgentConfigurationView: View {
    @Binding var node: WorkflowNode
    @State private var selectedAgentType: AgentType = .react
    @State private var selectedTools: Set<String> = []
    @State private var systemPrompt: String = ""
    @State private var maxIterations: Int = 10

    var body: some View {
        Form {
            Section("Agent Type") {
                Picker("Type", selection: $selectedAgentType) {
                    ForEach(AgentType.allCases, id: \.self) { type in
                        HStack {
                            Image(systemName: type.icon)
                            Text(type.displayName)
                        }
                        .tag(type)
                    }
                }
                .pickerStyle(.segmented)

                Text(selectedAgentType.description)
                    .font(.caption)
                    .foregroundColor(.secondary)
            }

            Section("Configuration") {
                TextField("System Prompt", text: $systemPrompt, axis: .vertical)
                    .lineLimit(3...6)

                Stepper("Max Iterations: \(maxIterations)", value: $maxIterations, in: 1...100)
            }

            Section("Tools") {
                ToolSelectionView(selectedTools: $selectedTools)
            }
        }
        .formStyle(.grouped)
        .onAppear {
            loadFromNode()
        }
        .onChange(of: selectedAgentType) { _, _ in
            saveToNode()
        }
        .onChange(of: selectedTools) { _, _ in
            saveToNode()
        }
        .onChange(of: systemPrompt) { _, _ in
            saveToNode()
        }
        .onChange(of: maxIterations) { _, _ in
            saveToNode()
        }
    }

    private func loadFromNode() {
        if let config = node.config {
            if case .string(let type) = config["agent_type"],
               let agentType = AgentType(rawValue: type) {
                selectedAgentType = agentType
            }
            if case .array(let toolsArray) = config["tools"] {
                let tools = toolsArray.compactMap { value -> String? in
                    if case .string(let toolName) = value { return toolName }
                    return nil
                }
                selectedTools = Set(tools)
            }
            if case .string(let prompt) = config["system_prompt"] {
                systemPrompt = prompt
            }
            if case .int(let iterations) = config["max_iterations"] {
                maxIterations = iterations
            }
        }
    }

    private func saveToNode() {
        var config = node.config ?? [:]
        config["agent_type"] = AnyCodableValue.string(selectedAgentType.rawValue)
        config["tools"] = AnyCodableValue.array(Array(selectedTools).map { AnyCodableValue.string($0) })
        config["system_prompt"] = AnyCodableValue.string(systemPrompt)
        config["max_iterations"] = AnyCodableValue.int(maxIterations)
        node.config = config
    }
}

// AgentType is defined in WorkflowTypes.swift

/// View for selecting tools to assign to an agent
struct ToolSelectionView: View {
    @Environment(WorkflowServiceGenerated.self) var workflowServiceGenerated
    @Binding var selectedTools: Set<String>
    @State private var availableTools: [ToolCategory] = []
    @State private var searchText = ""
    @State private var isLoading = false
    @State private var loadError: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            // Search field
            TextField("Search tools...", text: $searchText)
                .textFieldStyle(.roundedBorder)

            // Tool list
            if isLoading {
                ProgressView()
                    .frame(maxWidth: .infinity)
            } else if let error = loadError {
                VStack(spacing: 8) {
                    Image(systemName: "exclamationmark.triangle")
                        .foregroundColor(.orange)
                    Text("Failed to load tools")
                        .font(.headline)
                    Text(error)
                        .font(.caption)
                        .foregroundColor(.secondary)
                    Button("Retry") {
                        Task { await loadTools() }
                    }
                    .buttonStyle(.borderedProminent)
                }
                .frame(maxWidth: .infinity)
                .padding()
            } else if availableTools.isEmpty {
                Text("No tools available")
                    .foregroundColor(.secondary)
            } else {
                List {
                    ForEach(filteredCategories, id: \.name) { category in
                        DisclosureGroup {
                            ForEach(category.tools, id: \.name) { tool in
                                ToolRow(
                                    tool: tool,
                                    isSelected: selectedTools.contains(tool.name),
                                    onToggle: { toggleTool(tool.name) }
                                )
                            }
                        } label: {
                            HStack {
                                Image(systemName: category.icon)
                                Text(category.name)
                                    .font(.headline)
                                Spacer()
                                Text("\(selectedToolsInCategory(category)) / \(category.tools.count)")
                                    .font(.caption)
                                    .foregroundColor(.secondary)
                            }
                        }
                    }
                }
                .listStyle(.inset)
                .frame(maxHeight: 300)
            }

            // Selected count
            HStack {
                Text("\(selectedTools.count) tools selected")
                    .font(.caption)
                    .foregroundColor(.secondary)

                Spacer()

                Button("Clear All") {
                    selectedTools.removeAll()
                }
                .font(.caption)
                .disabled(selectedTools.isEmpty)
            }
        }
        .task {
            guard !Task.isCancelled else { return }
            await loadTools()
        }
    }

    private var filteredCategories: [ToolCategory] {
        if searchText.isEmpty {
            return availableTools
        }
        return availableTools.compactMap { category in
            let filteredTools = category.tools.filter { tool in
                tool.name.localizedCaseInsensitiveContains(searchText) ||
                    tool.description.localizedCaseInsensitiveContains(searchText)
            }
            if filteredTools.isEmpty {
                return nil
            }
            return ToolCategory(name: category.name, icon: category.icon, tools: filteredTools)
        }
    }

    private func selectedToolsInCategory(_ category: ToolCategory) -> Int {
        category.tools.filter { selectedTools.contains($0.name) }.count
    }

    private func toggleTool(_ name: String) {
        if selectedTools.contains(name) {
            selectedTools.remove(name)
        } else {
            selectedTools.insert(name)
        }
    }

    private func loadTools() async {
        isLoading = true
        loadError = nil
        defer { isLoading = false }

        do {
            // Load tools from backend registry
            let response = try await workflowServiceGenerated.listToolsGrouped()

            // Convert API response to local types
            availableTools = response.categories.map { category in
                ToolCategory(
                    name: category.displayName,
                    icon: iconForCategory(category.category),
                    tools: category.tools.map { tool in
                        ToolItem(name: tool.name, description: tool.description)
                    }
                )
            }

            logger.info("Loaded \(response.categories.count) tool categories")
        } catch {
            logger.error("Failed to load tools: \(error.localizedDescription)")
            loadError = error.localizedDescription

            // Use fallback data if backend unavailable
            availableTools = []
        }
    }

    /// Map category names to SF Symbol icons
    private func iconForCategory(_ category: String) -> String {
        switch category.lowercased() {
        case "transform": return "wand.and.stars"
        case "vision": return "eye"
        case "llm": return "brain"
        case "convert": return "arrow.triangle.2.circlepath"
        case "logic": return "arrow.triangle.branch"
        case "conditions": return "questionmark.diamond"
        case "file": return "folder"
        case "web": return "globe"
        case "mcp": return "puzzlepiece.extension"
        default: return "square.stack.3d.up"
        }
    }
}

/// Row displaying a single tool
struct ToolRow: View {
    let tool: ToolItem
    let isSelected: Bool
    let onToggle: () -> Void

    var body: some View {
        Button(action: onToggle) {
            HStack {
                Image(systemName: isSelected ? "checkmark.circle.fill" : "circle")
                    .foregroundColor(isSelected ? .accentColor : .secondary)

                VStack(alignment: .leading, spacing: 2) {
                    Text(tool.name)
                        .font(.body)
                    Text(tool.description)
                        .font(.caption)
                        .foregroundColor(.secondary)
                }

                Spacer()
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .padding(.vertical, 2)
    }
}

/// Tool category for grouping
struct ToolCategory {
    let name: String
    let icon: String
    let tools: [ToolItem]
}

/// Individual tool item
struct ToolItem {
    let name: String
    let description: String
}

#Preview {
    let ficheroClient = FicheroClient(libraryPath: "/tmp/preview.fichero")
    return AgentConfigurationView(
        node: .constant(WorkflowNode(
            tool: "agent",
            label: "Test Agent",
            positionX: 100,
            positionY: 100
        ))
    )
    .environment(WorkflowServiceGenerated(ficheroClient: ficheroClient))
}
