import OSLog
import SwiftUI

private let logger = Logger(subsystem: "app.fichero.fichero", category: "NodePopover")

/// Popover for configuring a workflow node
struct NodePopover: View {
    @Binding var node: WorkflowNode
    let allNodes: [WorkflowNode]
    let workflowId: String
    let onDelete: () -> Void
    let onDuplicate: () -> Void

    @State private var showAdvanced: Bool = false
    @State var showingNodeComparison = false

    // Provider/model loading — fileprivate so NodePopover+Comparison.swift can access them
    @State var providers: [NodeProviderModelSelector.ProviderOption] = []
    @State var isLoadingProviders: Bool = false
    @State var selectedProviderId: String = ""
    @State var selectedModelId: String = ""

    // Vision mode is now managed by the provider selector (Apple Vision = a provider)

    @Environment(ProviderAPIService.self) var providerService
    @Environment(DocumentStore.self) var documentStore: DocumentStore
    @Environment(SavedSearchService.self) var savedSearchService
    @Environment(WorkflowService.self) var workflowService
    @EnvironmentObject private var featureManager: FeatureManager

    // Dynamic prompt from backend (fetched based on current config)
    @State private var backendPrompt: String?
    @State private var isLoadingPrompt: Bool = false

    /// Get the tool info from the cached registry
    private var toolInfo: ToolInfo? {
        workflowService.getToolInfo(named: node.tool)
    }

    /// Get the current default prompt - from backend if available, otherwise nil
    private var currentDefaultPrompt: String? {
        // Use dynamically fetched prompt if available
        if let prompt = backendPrompt {
            return prompt
        }
        // Fall back to static default from tool info
        return toolInfo?.defaultPrompt
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            headerBar
            Divider()

            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    labelField

                    // Tool-specific configuration
                    toolConfigSection

                    // Prompt preview (LLM tools only)
                    PromptPreviewPanel(node: node)

                    if shouldShowProviderSection {
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
        .frame(minHeight: 400, maxHeight: 600)
        .background(Color(.windowBackgroundColor))
        .task {
            guard !Task.isCancelled else { return }
            // Initialize config states from node.config
            initConfigFromNode()
            // Load providers if section should be shown
            if shouldShowProviderSection {
                await loadProviders()
            }
        }
        .onChange(of: selectedProviderId) { _, newValue in
            // Load providers when switching away from Apple Vision to an LLM provider
            if newValue != appleVisionProviderId && !newValue.isEmpty && providers.isEmpty {
                Task { @MainActor in
                    await loadProviders()
                }
            }
        }
    }

    // MARK: - Tool Config Section

    @ViewBuilder
    private var toolConfigSection: some View {
        // Special cases that need custom UI (access to environment objects)
        switch node.tool {
        case "collection":
            CollectionNodeConfig(node: $node)
                .environment(documentStore)
        case "search":
            SearchNodeConfig(node: $node)
                .environment(savedSearchService)
        case "files":
            FilesNodeConfig(node: $node)
                .environment(documentStore)
        case "transcribe":
            TranscribeNodeConfig(
                node: $node,
                toolInfo: toolInfo,
                backendPrompt: backendPrompt
            )
        case "describe":
            DescribeNodeConfig(
                node: $node,
                toolInfo: toolInfo,
                backendPrompt: backendPrompt
            )
        case "summarize_file":
            SummarizeFileNodeConfig(node: $node)
        case "summarize_folder":
            SummarizeFolderNodeConfig(node: $node)
        case "summarize_collection":
            SummarizeCollectionNodeConfig(node: $node)
        case "extract_entities":
            ExtractEntitiesNodeConfig(node: $node)
        default:
            // Use dynamic config view for everything else
            if let info = toolInfo, !info.configSchema.isEmpty {
                DynamicConfigView(toolInfo: info, config: $node.config)
            } else {
                EmptyView()
            }
        }
    }

    // MARK: - Config Helpers

    private func initConfigFromNode() {
        // Restore provider selection from node config
        // For Apple Vision tools, check if vision_mode is "apple" to pre-select Apple Vision provider
        if toolSupportsAppleVision {
            if let configValue = node.config?["vision_mode"],
               case .string(let mode) = configValue, mode == "apple" {
                selectedProviderId = appleVisionProviderId
            } else if node.providerName == nil && node.config?["vision_mode"] == nil {
                // Default to Apple Vision for transcribe when no provider set
                selectedProviderId = appleVisionProviderId
            }
        }
    }

    // MARK: - Header

    private var headerBar: some View {
        HStack(spacing: 12) {
            Button(
                action: { Task { await loadProviders() } },
                label: {
                    Image(systemName: "arrow.clockwise")
                        .font(.caption)
                }
            )
            .buttonStyle(.plain)
            .foregroundColor(.secondary)

            HStack(spacing: 4) {
                Text(node.label ?? node.tool)
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

            TextField("Node label", text: Binding(
                get: { node.label ?? node.tool },
                set: { node.label = $0 }
            ))
            .textFieldStyle(.roundedBorder)
        }
    }

    // MARK: - Provider/Model Section

    private var providerModelSection: some View {
        NodeProviderModelSelector(
            node: $node,
            selectedProviderId: $selectedProviderId,
            selectedModelId: $selectedModelId,
            isLoadingProviders: $isLoadingProviders,
            providers: providers,
            toolRequiresVision: toolRequiresVision,
            toolSupportsAppleVision: toolSupportsAppleVision,
            onLoadProviders: loadProviders
        )
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
                if featureManager.isWorkflowEditorAdvancedViewsEnabled, !node.inputPorts.isEmpty {
                    inputMappingsSection
                }
            }
            .padding(.top, 8)
        }
    }

    private var inputMappingsSection: some View {
        NodeInputMappings(node: $node, allNodes: allNodes)
    }

    // MARK: - Actions Row

    var actionsRow: some View {
        VStack(spacing: 8) {
            if shouldShowProviderSection {
                compareModelsButton
            }

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
    }

    // MARK: - Helpers

    private var toolUsesLLM: Bool {
        node.usesLLM
    }

    /// All vision category tools that require vision-capable models
    private static let visionTools: Set<String> = [
        "transcribe", "describe", "analyze", "caption", "classify",
        "objects", "handwriting", "table_extract", "colors", "faces",
        "scene", "tags", "layout", "safety", "quality", "style",
        "extract", "diagram", "compare", "similarity"
    ]

    /// Tools that require vision-capable models
    private var toolRequiresVision: Bool {
        Self.visionTools.contains(node.tool)
    }

    /// Tools that support Apple Vision (on-device OCR) - only transcribe currently
    private static let appleVisionTools: Set<String> = ["transcribe"]

    /// Whether this tool supports switching between Apple Vision and LLM
    private var toolSupportsAppleVision: Bool {
        Self.appleVisionTools.contains(node.tool)
    }

    /// Whether to show the provider/model section
    private var shouldShowProviderSection: Bool {
        // Always show for Apple Vision tools (provider selector includes Apple Vision option)
        if toolSupportsAppleVision {
            return true
        }
        // For other vision tools (LLM-only), always show if it's a vision tool
        if toolRequiresVision {
            return true
        }
        // For non-vision tools, show if tool uses LLM
        return toolUsesLLM
    }

}

// MARK: - Preview

#Preview {
    let libraryManager = LibraryManager.shared
    let library = libraryManager.globalLibrary!

    NodePopover(
        node: .constant(WorkflowNode(
            tool: "transcribe",
            label: "Transcribe Text",
            positionX: 0,
            positionY: 0,
            inputPorts: [
                PortInfo(
                    id: "files", name: "Files", portType: "input",
                    dataType: "files", required: true, description: ""
                )
            ],
            outputPorts: [
                PortInfo(
                    id: "text", name: "Text", portType: "output",
                    dataType: "text", required: true, description: ""
                )
            ]
        )),
        allNodes: [],
        workflowId: "preview-workflow-id",
        onDelete: {},
        onDuplicate: {}
    )
    .environment(library.providerService)
    .environment(library.documentStore)
    .environment(library.savedSearchService)
    .environment(library.workflowService)
    .environmentObject(FeatureManager.shared)
}
