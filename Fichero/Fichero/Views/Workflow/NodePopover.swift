import SwiftUI

/// Popover for configuring a workflow node
struct NodePopover: View {
    @Binding var node: WorkflowNode
    let onDelete: () -> Void
    let onDuplicate: () -> Void

    @State private var showAdvanced: Bool = false

    // Provider/model loading
    @State private var providers: [LLMProvider] = []
    @State private var isLoadingProviders: Bool = false
    @State private var selectedProviderId: String = ""
    @State private var selectedModelId: String = ""

    private let chatService = ChatService()

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            headerBar
            Divider()

            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    labelField

                    if toolUsesLLM {
                        providerModelSection
                    }

                    advancedSection
                    Divider()
                    actionsRow
                }
                .padding()
            }
        }
        .frame(width: 320)
        .frame(minHeight: 200)
        .background(Color(.windowBackgroundColor))
        .task {
            if toolUsesLLM {
                await loadProviders()
            }
        }
    }

    // MARK: - Header

    private var headerBar: some View {
        HStack(spacing: 12) {
            Button(action: { Task { await loadProviders() } }) {
                Image(systemName: "arrow.clockwise")
                    .font(.caption)
            }
            .buttonStyle(.plain)
            .foregroundColor(.secondary)

            HStack(spacing: 4) {
                Text(node.label)
                    .font(.headline)
                Image(systemName: "pencil")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }

            Spacer()

            Toggle("", isOn: $node.enabled)
                .toggleStyle(.switch)
                .controlSize(.small)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 10)
        .background(Color(.controlBackgroundColor))
    }

    // MARK: - Label Field

    private var labelField: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("Label")
                .font(.caption)
                .foregroundColor(.secondary)

            TextField("Node label", text: $node.label)
                .textFieldStyle(.roundedBorder)
        }
    }

    // MARK: - Provider/Model Section

    private var providerModelSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                Text("Provider")
                    .font(.caption)
                    .foregroundColor(.secondary)

                if isLoadingProviders {
                    ProgressView()
                        .frame(maxWidth: .infinity, alignment: .leading)
                } else {
                    Picker("Provider", selection: $selectedProviderId) {
                        ForEach(providers.filter { $0.available }) { provider in
                            Text(provider.name).tag(provider.id)
                        }
                    }
                    .pickerStyle(.menu)
                    .onChange(of: selectedProviderId) { _, newValue in
                        node.providerName = providers.first(where: { $0.id == newValue })?.name
                        if let provider = providers.first(where: { $0.id == newValue }),
                           let firstModel = provider.models.first {
                            selectedModelId = firstModel
                            node.modelName = firstModel
                        }
                    }
                }
            }

            VStack(alignment: .leading, spacing: 4) {
                Text("Model")
                    .font(.caption)
                    .foregroundColor(.secondary)

                Picker("Model", selection: $selectedModelId) {
                    ForEach(providers.first(where: { $0.id == selectedProviderId })?.models ?? [], id: \.self) { model in
                        Text(model).tag(model)
                    }
                }
                .pickerStyle(.menu)
                .onChange(of: selectedModelId) { _, newValue in
                    node.modelName = newValue
                }
            }
        }
    }

    // MARK: - Advanced Section

    private var advancedSection: some View {
        DisclosureGroup("Advanced", isExpanded: $showAdvanced) {
            VStack(alignment: .leading, spacing: 12) {
                // Tool info
                HStack {
                    Text("Tool:")
                        .font(.caption)
                        .foregroundColor(.secondary)
                    Text(node.tool)
                        .font(.caption)
                }

                // Input mappings section
                if !node.inputPorts.isEmpty {
                    inputMappingsSection
                }
            }
            .padding(.top, 8)
        }
    }

    private var inputMappingsSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Input Mappings")
                .font(.caption)
                .fontWeight(.medium)
                .foregroundColor(.secondary)

            ForEach(node.inputPorts, id: \.id) { port in
                HStack(spacing: 8) {
                    // Port name label
                    HStack(spacing: 4) {
                        Circle()
                            .fill(colorForDataType(port.dataType))
                            .frame(width: 8, height: 8)
                        Text(port.name)
                            .font(.caption)
                            .frame(width: 60, alignment: .leading)
                    }

                    // Source path field
                    TextField(
                        "$.nodes.<id>.<key>",
                        text: bindingForMapping(portId: port.id)
                    )
                    .textFieldStyle(.roundedBorder)
                    .font(.caption)
                    .help("Path expression to data source (e.g., $.nodes.files_abc.files)")
                }
            }

            Text("Use path expressions like $.nodes.<nodeId>.<outputKey>")
                .font(.caption2)
                .foregroundColor(.secondary)
                .italic()
        }
    }

    // MARK: - Actions Row

    private var actionsRow: some View {
        HStack {
            Button(role: .destructive, action: onDelete) {
                Label("Delete", systemImage: "trash")
                    .font(.caption)
            }

            Spacer()

            Button(action: onDuplicate) {
                Label("Duplicate", systemImage: "doc.on.doc")
                    .font(.caption)
            }
        }
    }

    // MARK: - Helpers

    private func colorForDataType(_ dataType: String) -> Color {
        switch dataType {
        case "files", "file": return .green
        case "text": return .blue
        case "json": return .orange
        case "array": return .purple
        case "image": return .pink
        case "number": return .yellow
        case "boolean": return .red
        case "any": return .gray
        default: return .gray
        }
    }

    private func bindingForMapping(portId: String) -> Binding<String> {
        Binding(
            get: {
                node.inputMappings.first(where: { $0.portId == portId })?.sourcePath ?? ""
            },
            set: { newValue in
                // Update or add mapping
                if let index = node.inputMappings.firstIndex(where: { $0.portId == portId }) {
                    if newValue.isEmpty {
                        // Remove mapping if empty
                        node.inputMappings.remove(at: index)
                    } else {
                        // Update existing
                        node.inputMappings[index] = InputMapping(
                            portId: portId,
                            sourcePath: newValue,
                            transform: node.inputMappings[index].transform
                        )
                    }
                } else if !newValue.isEmpty {
                    // Add new mapping
                    node.inputMappings.append(InputMapping(
                        portId: portId,
                        sourcePath: newValue,
                        transform: nil
                    ))
                }
            }
        )
    }

    private var toolUsesLLM: Bool {
        node.usesLlm
    }

    private func loadProviders() async {
        guard providers.isEmpty && !isLoadingProviders else { return }
        isLoadingProviders = true
        defer { isLoadingProviders = false }

        do {
            providers = try await chatService.listProviders()

            if let providerName = node.providerName,
               let provider = providers.first(where: { $0.name == providerName }) {
                selectedProviderId = provider.id
                selectedModelId = node.modelName ?? provider.models.first ?? ""
            } else if let firstAvailable = providers.first(where: { $0.available }) {
                selectedProviderId = firstAvailable.id
                selectedModelId = firstAvailable.models.first ?? ""
                node.providerName = firstAvailable.name
                node.modelName = selectedModelId
            }
        } catch {
            NSLog("[NodePopover] Failed to load providers: \(error)")
        }
    }
}

// MARK: - Preview

#Preview {
    NodePopover(
        node: .constant(WorkflowNode(
            tool: "transcribe",
            label: "Transcribe Text",
            inputPorts: [
                PortInfo(id: "files", name: "Files", portType: "input", dataType: "files", required: true, description: "")
            ],
            outputPorts: [
                PortInfo(id: "text", name: "Text", portType: "output", dataType: "text", required: true, description: "")
            ],
            positionX: 0,
            positionY: 0
        )),
        onDelete: {},
        onDuplicate: {}
    )
}
