import SwiftUI
import OSLog

// swiftlint:disable file_length type_body_length

private let logger = Logger(subsystem: "ca.tubb.Fichero", category: "NodePopover")

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

    // Tool-specific config states
    @State private var collectionId: String = ""
    @State private var promptText: String = ""
    @State private var language: String = "en"

    // Describe config
    @State private var detailLevel: String = "detailed"
    @State private var focusText: String = ""

    // Summarize config
    @State private var summaryStyle: String = "brief"
    @State private var maxLength: Int = 200
    @State private var includeThemes: Bool = true
    @State private var includeStatistics: Bool = true

    // Entity extraction config
    @State private var entityTypes: Set<String> = ["people", "organizations", "locations", "dates"]
    @State private var includeContext: Bool = false

    // Vision mode for transcribe/describe
    @State private var visionMode: String = "apple"  // "apple" or "llm"
    @State private var maxImageDimension: Double = 2048  // Image size limit for vision API (default 2048)

    // Search config
    @State private var selectedSearchId: String = ""

    // Files config
    @State private var selectedFileIds: [String] = []

    @EnvironmentObject var chatService: ChatServiceGenerated
    @EnvironmentObject var documentStore: DocumentStore
    @EnvironmentObject var savedSearchServiceGenerated: SavedSearchServiceGenerated
    @EnvironmentObject var workflowService: WorkflowServiceGenerated

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
        .onChange(of: visionMode) { _, newValue in
            // Load providers when switching to LLM mode
            if newValue == "llm" && providers.isEmpty {
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
            collectionConfigSection
        case "search":
            searchConfigSection
        case "files":
            filesConfigSection
        case "transcribe":
            transcribeConfigSection
        case "describe":
            describeConfigSection
        default:
            // Use dynamic config view for everything else
            if let info = toolInfo, !info.configSchema.isEmpty {
                DynamicConfigView(toolInfo: info, config: $node.config)
            } else {
                EmptyView()
            }
        }
    }

    private var collectionConfigSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Collection")
                .font(.caption)
                .foregroundColor(.secondary)

            Picker("Select collection", selection: $collectionId) {
                Text("Select...").tag("")
                ForEach(documentStore.collections.filter { $0.docType == .folder }, id: \.id) { folder in
                    Text(folder.name).tag(folder.id)
                }
            }
            .pickerStyle(.menu)
            .onChange(of: collectionId) { _, newValue in
                updateConfig(key: "collection_id", value: .string(newValue))
            }
        }
    }

    private var transcribeConfigSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            // Vision Mode selector
            VStack(alignment: .leading, spacing: 4) {
                Text("Vision Engine")
                    .font(.caption)
                    .foregroundColor(.secondary)

                Picker("Vision Engine", selection: $visionMode) {
                    Label("Apple Vision (On-Device)", systemImage: "apple.logo")
                        .tag("apple")
                    Label("Vision LLM (Cloud)", systemImage: "cloud")
                        .tag("llm")
                }
                .pickerStyle(.menu)
                .onChange(of: visionMode) { _, newValue in
                    updateConfig(key: "vision_mode", value: .string(newValue))
                    node.usesLLM = (newValue == "llm")
                    // Clear provider/model when switching to Apple Vision
                    if newValue == "apple" {
                        node.providerName = nil
                        node.modelName = nil
                    }
                }
            }

            // Language
            VStack(alignment: .leading, spacing: 4) {
                Text("Language")
                    .font(.caption)
                    .foregroundColor(.secondary)

                TextField("Language code (e.g., en, es, fr)", text: $language)
                    .textFieldStyle(.roundedBorder)
                    .onChange(of: language) { _, newValue in
                        updateConfig(key: "language", value: .string(newValue))
                    }
            }

            // Image Size (only for LLM mode)
            if visionMode == "llm" {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Max Image Size")
                        .font(.caption)
                        .foregroundColor(.secondary)

                    Picker("Max Image Size", selection: $maxImageDimension) {
                        Text("512px (Fastest)").tag(512.0)
                        Text("768px (Fast)").tag(768.0)
                        Text("1024px (Balanced)").tag(1024.0)
                        Text("1536px (Detailed)").tag(1536.0)
                        Text("2048px (Default)").tag(2048.0)
                        Text("Original Size (Maximum)").tag(0.0)
                    }
                    .pickerStyle(.menu)
                    .onChange(of: maxImageDimension) { _, newValue in
                        updateConfig(key: "max_image_dimension", value: .int(Int(newValue)))
                    }

                    Text("Smaller = faster, original = full detail")
                        .font(.caption2)
                        .foregroundColor(.secondary)
                }
            }

            // Custom prompt (only for LLM mode)
            if visionMode == "llm" {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Prompt")
                        .font(.caption)
                        .foregroundColor(.secondary)

                    ZStack(alignment: .topLeading) {
                        // Placeholder showing default prompt from backend
                        if promptText.isEmpty, let defaultPrompt = currentDefaultPrompt {
                            Text(defaultPrompt)
                                .font(.caption)
                                .foregroundColor(.secondary.opacity(0.7))
                                .padding(.horizontal, 4)
                                .padding(.vertical, 8)
                        }

                        TextEditor(text: $promptText)
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
                    .onChange(of: promptText) { _, newValue in
                        if newValue.isEmpty {
                            removeConfig(key: "prompt")
                        } else {
                            updateConfig(key: "prompt", value: .string(newValue))
                        }
                    }

                    Text("Edit to customize, or clear to use default")
                        .font(.caption2)
                        .foregroundColor(.secondary)
                }
            }
        }
    }

    private var searchConfigSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Saved Search")
                .font(.caption)
                .foregroundColor(.secondary)

            Picker("Select saved search", selection: $selectedSearchId) {
                Text("Select...").tag("")
                ForEach(savedSearchServiceGenerated.savedSearches) { search in
                    Text(search.name).tag(search.id)
                }
            }
            .pickerStyle(.menu)
            .onChange(of: selectedSearchId) { _, newValue in
                updateConfig(key: "search_id", value: .string(newValue))
                // Also store the query for display purposes
                let searches = savedSearchServiceGenerated.savedSearches
                if let search = searches.first(where: { $0.id == newValue }) {
                    updateConfig(key: "query", value: .string(search.query))
                }
            }

            if savedSearchServiceGenerated.savedSearches.isEmpty {
                Text("No saved searches. Create one from the Search view.")
                    .font(.caption2)
                    .foregroundColor(.secondary)
                    .italic()
            }
        }
        .task {
            // Load saved searches if not already loaded
            if savedSearchServiceGenerated.savedSearches.isEmpty {
                try? await savedSearchServiceGenerated.loadSavedSearches()
            }
        }
    }

    // MARK: - Files Config

    private var filesConfigSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Selected Files")
                .font(.caption)
                .foregroundColor(.secondary)

            // List of selected files
            if selectedFileIds.isEmpty {
                dropZoneView
            } else {
                VStack(spacing: 4) {
                    ForEach(selectedFileIds, id: \.self) { fileId in
                        fileRow(fileId: fileId)
                    }

                    // Add more files drop zone
                    dropZoneView
                }
            }
        }
    }

    private var dropZoneView: some View {
        RoundedRectangle(cornerRadius: 6)
            .strokeBorder(style: StrokeStyle(lineWidth: 1, dash: [5]))
            .foregroundColor(.secondary)
            .frame(height: 44)
            .overlay(
                HStack {
                    Image(systemName: "plus.circle")
                    Text("Drop files here or select from library")
                        .font(.caption)
                }
                .foregroundColor(.secondary)
            )
            .onDrop(of: [.plainText], isTargeted: nil) { providers in
                handleFileDrop(providers)
            }
            .contentShape(Rectangle())
            .onTapGesture {
                showFilePickerSheet()
            }
    }

    @ViewBuilder
    private func fileRow(fileId: String) -> some View {
        // Look up document name from current documents or collections
        let allDocs = documentStore.currentDocuments + documentStore.collections
        let docName = allDocs.first(where: { $0.id == fileId })?.name ?? "Document \(fileId.prefix(8))..."

        HStack {
            Image(systemName: "doc")
                .foregroundColor(.secondary)
            Text(docName)
                .font(.caption)
                .lineLimit(1)
            Spacer()
            Button {
                removeFile(fileId)
            } label: {
                Image(systemName: "xmark.circle.fill")
                    .foregroundColor(.secondary)
            }
            .buttonStyle(.plain)
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 4)
        .background(Color(.controlBackgroundColor))
        .cornerRadius(4)
    }

    private func removeFile(_ fileId: String) {
        selectedFileIds.removeAll { $0 == fileId }
        updateConfig(key: "file_ids", value: .array(selectedFileIds.map { .string($0) }))
    }

    private func handleFileDrop(_ providers: [NSItemProvider]) -> Bool {
        for provider in providers {
            _ = provider.loadObject(ofClass: String.self) { string, _ in
                guard let docId = string else { return }
                Task { @MainActor in
                    if !self.selectedFileIds.contains(docId) {
                        self.selectedFileIds.append(docId)
                        self.updateConfig(
                            key: "file_ids",
                            value: .array(self.selectedFileIds.map { .string($0) })
                        )
                    }
                }
            }
        }
        return true
    }

    private func showFilePickerSheet() {
        // For now, users can drag files from the library browser
        // A picker sheet could be added in the future
        logger.debug("File picker sheet would open here")
    }

    // MARK: - Describe Config

    private var describeConfigSection: some View {
        // Describe tool ONLY supports LLM vision (no Apple Vision)
        // The backend hardcodes vision_mode="llm" since it requires semantic understanding
        VStack(alignment: .leading, spacing: 12) {
            // Detail level
            VStack(alignment: .leading, spacing: 4) {
                Text("Detail Level")
                    .font(.caption)
                    .foregroundColor(.secondary)

                Picker("", selection: $detailLevel) {
                    Text("Brief").tag("brief")
                    Text("Detailed").tag("detailed")
                    Text("Comprehensive").tag("comprehensive")
                }
                .labelsHidden()
                .pickerStyle(.segmented)
                .onChange(of: detailLevel) { _, newValue in
                    updateConfig(key: "detail_level", value: .string(newValue))
                }
            }

            // Focus
            VStack(alignment: .leading, spacing: 4) {
                Text("Focus (optional)")
                    .font(.caption)
                    .foregroundColor(.secondary)

                TextField("e.g., people, objects, text, scene", text: $focusText)
                    .textFieldStyle(.roundedBorder)
                    .onChange(of: focusText) { _, newValue in
                        if newValue.isEmpty {
                            removeConfig(key: "focus")
                        } else {
                            updateConfig(key: "focus", value: .string(newValue))
                        }
                    }
            }

            // Custom prompt
            VStack(alignment: .leading, spacing: 4) {
                Text("Prompt")
                    .font(.caption)
                    .foregroundColor(.secondary)

                ZStack(alignment: .topLeading) {
                    // Placeholder showing default prompt from backend
                    if promptText.isEmpty, let defaultPrompt = currentDefaultPrompt {
                        Text(defaultPrompt)
                            .font(.caption)
                            .foregroundColor(.secondary.opacity(0.7))
                            .padding(.horizontal, 4)
                            .padding(.vertical, 8)
                    }

                    TextEditor(text: $promptText)
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
                .onChange(of: promptText) { _, newValue in
                    if newValue.isEmpty {
                        removeConfig(key: "prompt")
                    } else {
                        updateConfig(key: "prompt", value: .string(newValue))
                    }
                }

                Text("Edit to customize, or clear to use default")
                    .font(.caption2)
                    .foregroundColor(.secondary)
            }
        }
    }

    // MARK: - Summarize File Config

    private var summarizeFileConfigSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            // Style
            VStack(alignment: .leading, spacing: 4) {
                Text("Style")
                    .font(.caption)
                    .foregroundColor(.secondary)

                Picker("Style", selection: $summaryStyle) {
                    Text("Brief").tag("brief")
                    Text("Detailed").tag("detailed")
                    Text("Bullets").tag("bullets")
                }
                .pickerStyle(.segmented)
                .onChange(of: summaryStyle) { _, newValue in
                    updateConfig(key: "style", value: .string(newValue))
                }
            }

            // Max length
            VStack(alignment: .leading, spacing: 4) {
                Text("Max Words: \(maxLength)")
                    .font(.caption)
                    .foregroundColor(.secondary)

                Slider(value: Binding(
                    get: { Double(maxLength) },
                    set: { maxLength = Int($0) }
                ), in: 50...1000, step: 50)
                .onChange(of: maxLength) { _, newValue in
                    updateConfig(key: "max_length", value: .int(newValue))
                }
            }

            // Custom prompt
            VStack(alignment: .leading, spacing: 4) {
                Text("Custom Prompt (optional)")
                    .font(.caption)
                    .foregroundColor(.secondary)

                TextEditor(text: $promptText)
                    .frame(minHeight: 60)
                    .font(.caption)
                    .overlay(
                        RoundedRectangle(cornerRadius: 4)
                            .stroke(Color(.separatorColor), lineWidth: 1)
                    )
                    .onChange(of: promptText) { _, newValue in
                        if newValue.isEmpty {
                            removeConfig(key: "prompt")
                        } else {
                            updateConfig(key: "prompt", value: .string(newValue))
                        }
                    }
            }
        }
    }

    // MARK: - Summarize Folder Config

    private var summarizeFolderConfigSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            // Style
            VStack(alignment: .leading, spacing: 4) {
                Text("Style")
                    .font(.caption)
                    .foregroundColor(.secondary)

                Picker("Style", selection: $summaryStyle) {
                    Text("Brief").tag("brief")
                    Text("Detailed").tag("detailed")
                    Text("Bullets").tag("bullets")
                }
                .pickerStyle(.segmented)
                .onChange(of: summaryStyle) { _, newValue in
                    updateConfig(key: "style", value: .string(newValue))
                }
            }

            // Max length
            VStack(alignment: .leading, spacing: 4) {
                Text("Max Words: \(maxLength)")
                    .font(.caption)
                    .foregroundColor(.secondary)

                Slider(value: Binding(
                    get: { Double(maxLength) },
                    set: { maxLength = Int($0) }
                ), in: 100...2000, step: 100)
                .onChange(of: maxLength) { _, newValue in
                    updateConfig(key: "max_length", value: .int(newValue))
                }
            }

            // Include themes
            Toggle("Include Themes", isOn: $includeThemes)
                .font(.caption)
                .onChange(of: includeThemes) { _, newValue in
                    updateConfig(key: "include_themes", value: .bool(newValue))
                }
        }
    }

    // MARK: - Summarize Collection Config

    private var summarizeCollectionConfigSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            // Style
            VStack(alignment: .leading, spacing: 4) {
                Text("Style")
                    .font(.caption)
                    .foregroundColor(.secondary)

                Picker("Style", selection: $summaryStyle) {
                    Text("Executive").tag("executive")
                    Text("Detailed").tag("detailed")
                    Text("Narrative").tag("narrative")
                }
                .pickerStyle(.segmented)
                .onChange(of: summaryStyle) { _, newValue in
                    updateConfig(key: "style", value: .string(newValue))
                }
            }

            // Max length
            VStack(alignment: .leading, spacing: 4) {
                Text("Max Words: \(maxLength)")
                    .font(.caption)
                    .foregroundColor(.secondary)

                Slider(value: Binding(
                    get: { Double(maxLength) },
                    set: { maxLength = Int($0) }
                ), in: 200...3000, step: 100)
                .onChange(of: maxLength) { _, newValue in
                    updateConfig(key: "max_length", value: .int(newValue))
                }
            }

            // Include statistics
            Toggle("Include Statistics", isOn: $includeStatistics)
                .font(.caption)
                .onChange(of: includeStatistics) { _, newValue in
                    updateConfig(key: "include_statistics", value: .bool(newValue))
                }
        }
    }

    // MARK: - Extract Entities Config

    private var extractEntitiesConfigSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            // Entity types
            VStack(alignment: .leading, spacing: 8) {
                Text("Entity Types")
                    .font(.caption)
                    .foregroundColor(.secondary)

                let entityTypeOptions = ["people", "organizations", "locations", "dates", "events", "products"]
                LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 8) {
                    ForEach(entityTypeOptions, id: \.self) { type in
                        Toggle(type.capitalized, isOn: Binding(
                            get: { entityTypes.contains(type) },
                            set: { isOn in
                                if isOn {
                                    entityTypes.insert(type)
                                } else {
                                    entityTypes.remove(type)
                                }
                                updateConfig(key: "entity_types", value: .array(entityTypes.map { .string($0) }))
                            }
                        ))
                        .toggleStyle(.checkbox)
                        .font(.caption)
                    }
                }
            }

            // Include context
            Toggle("Include Context", isOn: $includeContext)
                .font(.caption)
                .onChange(of: includeContext) { _, newValue in
                    updateConfig(key: "include_context", value: .bool(newValue))
                }

            Text("Shows surrounding text for each entity")
                .font(.caption2)
                .foregroundColor(.secondary)
        }
    }

    // MARK: - Config Helpers

    private func initConfigFromNode() {
        // Initialize state from node.config
        collectionId = getConfigString("collection_id")
        promptText = getConfigString("prompt")
        language = getConfigString("language").isEmpty ? "en" : getConfigString("language")

        // Vision mode only applies to tools that support Apple Vision (transcribe)
        // Default to "apple" for transcribe, "llm" for all other vision tools
        if Self.appleVisionTools.contains(node.tool) {
            visionMode = getConfigString("vision_mode").isEmpty ? "apple" : getConfigString("vision_mode")
        } else {
            visionMode = "llm"  // All other vision tools only support LLM
        }

        // Describe config
        detailLevel = getConfigString("detail_level").isEmpty ? "detailed" : getConfigString("detail_level")
        focusText = getConfigString("focus")

        // Summarize config
        summaryStyle = getConfigString("style").isEmpty ? "brief" : getConfigString("style")
        maxLength = getConfigInt("max_length", defaultValue: 200)
        includeThemes = getConfigBool("include_themes", defaultValue: true)
        includeStatistics = getConfigBool("include_statistics", defaultValue: true)

        // Entity extraction config
        if let types = getConfigStringArray("entity_types"), !types.isEmpty {
            entityTypes = Set(types)
        }
        includeContext = getConfigBool("include_context", defaultValue: false)

        // Search config
        selectedSearchId = getConfigString("search_id")

        // Files config
        if let fileIds = getConfigStringArray("file_ids") {
            selectedFileIds = fileIds
        }
    }

    private func getConfigString(_ key: String) -> String {
        guard let config = node.config, let value = config[key] else { return "" }
        if case .string(let str) = value {
            return str
        }
        return ""
    }

    private func getConfigInt(_ key: String, defaultValue: Int) -> Int {
        guard let config = node.config, let value = config[key] else { return defaultValue }
        if case .int(let intVal) = value {
            return intVal
        }
        if case .double(let doubleVal) = value {
            return Int(doubleVal)
        }
        return defaultValue
    }

    private func getConfigBool(_ key: String, defaultValue: Bool) -> Bool {
        guard let config = node.config, let value = config[key] else { return defaultValue }
        if case .bool(let boolVal) = value {
            return boolVal
        }
        return defaultValue
    }

    private func getConfigStringArray(_ key: String) -> [String]? {
        guard let config = node.config, let value = config[key] else { return nil }
        if case .array(let arr) = value {
            return arr.compactMap { item in
                if case .string(let str) = item {
                    return str
                }
                return nil
            }
        }
        return nil
    }

    private func updateConfig(key: String, value: AnyCodableValue) {
        if node.config == nil {
            node.config = [:]
        }
        node.config?[key] = value
    }

    private func removeConfig(key: String) {
        node.config?.removeValue(forKey: key)
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
        VStack(alignment: .leading, spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                Text("Provider")
                    .font(.caption)
                    .foregroundColor(.secondary)

                if isLoadingProviders {
                    ProgressView()
                        .frame(maxWidth: .infinity, alignment: .leading)
                } else if providers.isEmpty {
                    Text("No providers configured")
                        .font(.caption)
                        .foregroundColor(.orange)
                } else {
                    // Filter for available providers, and vision-capable if tool requires it
                    let availableProviders = providers.filter { provider in
                        guard provider.available else { return false }
                        if toolRequiresVision {
                            return provider.supportsVision
                        }
                        return true
                    }
                    if availableProviders.isEmpty {
                        if toolRequiresVision {
                            Text("No vision-capable providers available")
                                .font(.caption)
                                .foregroundColor(.orange)
                        } else {
                            Text("No providers available")
                                .font(.caption)
                                .foregroundColor(.orange)
                        }
                    } else {
                        Picker("Provider", selection: $selectedProviderId) {
                            Text("Select provider...").tag("")
                            ForEach(availableProviders) { provider in
                                Text(provider.name).tag(provider.id)
                            }
                        }
                        .pickerStyle(.menu)
                        .onChange(of: selectedProviderId) { _, newValue in
                            guard !newValue.isEmpty else { return }
                            // Use provider ID (e.g. "openrouter") not display name (e.g. "OpenRouter")
                            // The backend expects the provider type ID
                            node.providerName = newValue
                            print("[DEBUG] Provider selected: id=\(newValue)")
                            if let provider = providers.first(where: { $0.id == newValue }),
                               let firstModel = provider.models.first {
                                selectedModelId = firstModel
                                node.modelName = firstModel
                                print("[DEBUG] Model set to: \(firstModel)")
                            }
                            print(
                                "[DEBUG] Node after update: providerName=\(node.providerName ?? "nil"), " +
                                "modelName=\(node.modelName ?? "nil")"
                            )
                        }
                    }
                }
            }

            VStack(alignment: .leading, spacing: 4) {
                Text("Model")
                    .font(.caption)
                    .foregroundColor(.secondary)

                let selectedProvider = providers.first { $0.id == selectedProviderId }
                let models = selectedProvider?.models ?? []
                if models.isEmpty {
                    Text("Select a provider first")
                        .font(.caption)
                        .foregroundColor(.secondary)
                } else {
                    Picker("Model", selection: $selectedModelId) {
                        Text("Select model...").tag("")
                        ForEach(models, id: \.self) { model in
                            Text(model).tag(model)
                        }
                    }
                    .pickerStyle(.menu)
                    .onChange(of: selectedModelId) { _, newValue in
                        guard !newValue.isEmpty else { return }
                        node.modelName = newValue
                        print("[DEBUG] Model manually selected: \(newValue), node.modelName=\(node.modelName ?? "nil")")
                    }
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
        // For tools that support Apple Vision switching, only show when using LLM mode
        if toolSupportsAppleVision {
            return visionMode == "llm"
        }
        // For other vision tools (LLM-only), always show if it's a vision tool
        if toolRequiresVision {
            return true
        }
        // For non-vision tools, show if tool uses LLM
        return toolUsesLLM
    }

    private func loadProviders() async {
        guard !isLoadingProviders else { return }
        isLoadingProviders = true
        defer { isLoadingProviders = false }

        do {
            providers = try await chatService.listProviders()
            logger.info("Loaded \(providers.count) providers, \(providers.filter { $0.available }.count) available")

            // Restore selection from node if set
            // providerName now stores the provider ID (e.g. "openrouter")
            if let providerId = node.providerName,
               let provider = providers.first(where: { $0.id == providerId }) {
                selectedProviderId = provider.id
                selectedModelId = node.modelName ?? provider.models.first ?? ""
            }
            // Don't auto-select a provider - let user choose
        } catch {
            logger.error("Failed to load providers: \(String(describing: error))")
        }
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
        onDelete: {},
        onDuplicate: {}
    )
    .environmentObject(library.chatServiceGenerated)
    .environmentObject(library.documentStore)
    .environmentObject(library.savedSearchServiceGenerated)
    .environmentObject(library.workflowServiceGenerated)
}

// swiftlint:enable file_length type_body_length
