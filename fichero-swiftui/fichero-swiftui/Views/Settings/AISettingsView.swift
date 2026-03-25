import OSLog
import SwiftUI

private let logger = Logger(subsystem: "com.tubb.Fichero", category: "Settings")

// MARK: - AI Settings

/// Settings for default AI models with Defaults and Advanced sub-tabs
struct AISettingsView: View {
    @EnvironmentObject var appState: AppState
    @ObservedObject var featureManager = FeatureManager.shared

    @State private var defaults = AIDefaults()
    @State private var isLoading = true
    @State private var isSaving = false
    @State private var errorMessage: String?
    @State private var selectedTab = 0

    // Model lists per category
    @State private var textModels: [ModelInfo] = []
    @State private var visionModels: [ModelInfo] = []
    @State private var audioModels: [ModelInfo] = []
    @State private var videoModels: [ModelInfo] = []

    var body: some View {
        VStack(spacing: 0) {
            if !appState.isBackendRunning {
                Form {
                    Section {
                        Label("Backend not connected", systemImage: "exclamationmark.triangle")
                            .foregroundStyle(.secondary)
                    }
                }
                .padding()
            } else if isLoading {
                Form {
                    Section {
                        ProgressView("Loading defaults...")
                    }
                }
                .padding()
            } else {
                if featureManager.isSettingsAIAdvancedTabEnabled {
                    Picker("", selection: $selectedTab) {
                        Text("Defaults").tag(0)
                        Text("Advanced").tag(1)
                    }
                    .pickerStyle(.segmented)
                    .padding(.horizontal)
                    .padding(.top, 8)
                }

                if !featureManager.isSettingsAIAdvancedTabEnabled || selectedTab == 0 {
                    defaultsTab
                } else {
                    advancedTab
                }
            }

            if let error = errorMessage {
                Text(error)
                    .foregroundStyle(.red)
                    .font(.caption)
                    .padding(.horizontal)
                    .padding(.bottom, 4)
            }
        }
        .task {
            guard !Task.isCancelled else { return }
            await loadDefaults()
        }
        .onChange(of: defaults) {
            Task {
                await saveDefaults()
            }
        }
    }

    // MARK: - Defaults Tab

    @ViewBuilder
    private var defaultsTab: some View {
        ScrollView {
            VStack(spacing: 12) {
                categoryGroupBox(
                    title: "Text",
                    description: "Used by Summarize, Extract, and Classify tools.",
                    providerBinding: $defaults.textProvider,
                    modelBinding: $defaults.textModel,
                    models: textModels
                )

                categoryGroupBox(
                    title: "Vision",
                    description: "Used by Describe and Analyze tools for image understanding.",
                    providerBinding: $defaults.visionProvider,
                    modelBinding: $defaults.visionModel,
                    models: visionModels
                )

                if featureManager.isWorkflowToolsAudioEnabled {
                    categoryGroupBox(
                        title: "Audio",
                        description: "Used by Transcription tools for speech-to-text.",
                        providerBinding: $defaults.audioProvider,
                        modelBinding: $defaults.audioModel,
                        models: audioModels
                    )
                }

                if featureManager.isWorkflowToolsVideoEnabled {
                    categoryGroupBox(
                        title: "Video",
                        description: "Used by video analysis tools.",
                        providerBinding: $defaults.videoProvider,
                        modelBinding: $defaults.videoModel,
                        models: videoModels
                    )
                }

                HStack {
                    Label(
                        "Per-tool overrides in the workflow editor take precedence over these defaults.",
                        systemImage: "info.circle"
                    )
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    Spacer()
                }

                HStack {
                    Button("Reset All Defaults", role: .destructive) {
                        Task { await resetDefaults() }
                    }
                    Spacer()
                }
            }
            .padding()
        }
        .onChange(of: defaults.textProvider) { _, newValue in
            loadModels(for: newValue, into: $textModels)
        }
        .onChange(of: defaults.visionProvider) { _, newValue in
            loadModels(for: newValue, into: $visionModels)
        }
        .onChange(of: defaults.audioProvider) { _, newValue in
            loadModels(for: newValue, into: $audioModels)
        }
        .onChange(of: defaults.videoProvider) { _, newValue in
            loadModels(for: newValue, into: $videoModels)
        }
    }

    @ViewBuilder
    func categoryGroupBox(
        title: String,
        description: String,
        providerBinding: Binding<String>,
        modelBinding: Binding<String>,
        models: [ModelInfo]
    ) -> some View {
        GroupBox {
            VStack(alignment: .leading, spacing: 8) {
                Text(description)
                    .font(.caption)
                    .foregroundStyle(.secondary)

                providerPicker(selection: providerBinding)
                modelPicker(selection: modelBinding, models: models)
            }
        } label: {
            Text(title)
                .font(.headline)
        }
    }

    // MARK: - Advanced Tab

    @ViewBuilder
    private var advancedTab: some View {
        Form {
            Section("Embeddings") {
                Picker("Model", selection: $defaults.embeddingsModel) {
                    Text("multilingual-e5-large (default)").tag("")
                    Text("multilingual-e5-large").tag("intfloat/multilingual-e5-large")
                    Text("multilingual-e5-base (smaller)").tag("intfloat/multilingual-e5-base")
                    Text("bge-small-en (fast, English)").tag("BAAI/bge-small-en-v1.5")
                    Text("all-MiniLM-L6-v2 (tiny, English)").tag("all-MiniLM-L6-v2")
                }
                Text("Changing model requires re-indexing all documents")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Section("Generation") {
                HStack {
                    Text("Temperature")
                    Slider(value: temperatureBinding, in: 0...2, step: 0.1)
                    Text(temperatureDisplay)
                        .monospacedDigit()
                        .frame(width: 30)
                }
                TextField("Max Tokens", text: $defaults.maxTokens)
                    .textFieldStyle(.roundedBorder)
            }

            Section("Prompt") {
                TextField("Prompt Prefix (prepended to all prompts)", text: $defaults.promptPrefix, axis: .vertical)
                    .lineLimit(3...6)
            }
        }
        .padding()
    }
}

// MARK: - Helpers

private extension AISettingsView {
    var temperatureBinding: Binding<Double> {
        Binding(
            get: { Double(defaults.temperature) ?? 0.7 },
            set: { defaults.temperature = String(format: "%.1f", $0) }
        )
    }

    var temperatureDisplay: String {
        defaults.temperature.isEmpty ? "0.7" : defaults.temperature
    }

    @ViewBuilder
    func providerPicker(selection: Binding<String>) -> some View {
        Picker("Provider", selection: selection) {
            Text("None").tag("")
            ForEach(
                appState.providers.filter { featureManager.isProviderTypeEnabled($0.providerType) },
                id: \.providerType
            ) { provider in
                Text(provider.name).tag(provider.providerType)
            }
        }
    }

    @ViewBuilder
    func modelPicker(selection: Binding<String>, models: [ModelInfo]) -> some View {
        let currentSelection = selection.wrappedValue
        let hasCurrentSelection = !currentSelection.isEmpty
        let hasCurrentInList = models.contains { $0.modelId == currentSelection }

        Picker("Model", selection: selection) {
            Text("None").tag("")
            if hasCurrentSelection && !hasCurrentInList {
                Text("\(currentSelection) (saved)").tag(currentSelection)
            }
            ForEach(models, id: \.modelId) { model in
                Text(model.fullName).tag(model.modelId)
            }
        }
    }

    func loadModels(for providerType: String, into models: Binding<[ModelInfo]>) {
        guard !providerType.isEmpty else {
            models.wrappedValue = []
            return
        }

        guard let provider = appState.providers.first(where: { $0.providerType == providerType }) else {
            models.wrappedValue = []
            return
        }

        Task {
            do {
                let configuredModels = try await appState.providerService.listProviderModels(providerId: provider.id)
                models.wrappedValue = configuredModels.map { userModel in
                    ModelInfo(
                        modelId: userModel.modelId,
                        fullName: userModel.name,
                        description: nil,
                        isRecommended: false,
                        isLocal: false,
                        inputCostPerMillion: 0,
                        outputCostPerMillion: 0,
                        batchInputCostPerMillion: nil,
                        batchOutputCostPerMillion: nil,
                        cacheReadCostPerMillion: nil,
                        maxInputTokens: nil,
                        maxOutputTokens: nil,
                        mode: nil,
                        supportsVision: userModel.capabilities.contains("vision"),
                        supportsFunctionCalling: userModel.capabilities.contains("tools"),
                        supportsAudioInput: userModel.capabilities.contains("audio"),
                        supportsAudioOutput: false,
                        supportsPdfInput: false,
                        supportsPromptCaching: false,
                        supportsReasoning: false,
                        supportsWebSearch: false,
                        supportsStreaming: false,
                        supportsBatchApi: false,
                        provider: providerType
                    )
                }
            } catch {
                logger.error("Failed to load models for \(providerType): \(error.localizedDescription)")
            }
        }
    }

    func loadDefaults() async {
        isLoading = true
        defer { isLoading = false }
        do {
            defaults = try await appState.fetchAIDefaults()
            if !defaults.textProvider.isEmpty {
                loadModels(for: defaults.textProvider, into: $textModels)
            }
            if !defaults.visionProvider.isEmpty {
                loadModels(for: defaults.visionProvider, into: $visionModels)
            }
            if !defaults.audioProvider.isEmpty {
                loadModels(for: defaults.audioProvider, into: $audioModels)
            }
            if !defaults.videoProvider.isEmpty {
                loadModels(for: defaults.videoProvider, into: $videoModels)
            }
        } catch {
            logger.error("Failed to load AI defaults: \(error.localizedDescription)")
            errorMessage = "Failed to load: \(error.localizedDescription)"
        }
    }

    func saveDefaults() async {
        guard !isLoading else { return }
        isSaving = true
        defer { isSaving = false }
        do {
            try await appState.saveAIDefaults(defaults)
            errorMessage = nil
        } catch {
            logger.error("Failed to save AI defaults: \(error.localizedDescription)")
            errorMessage = "Failed to save: \(error.localizedDescription)"
        }
    }

    func resetDefaults() async {
        do {
            try await appState.resetAIDefaults()
            defaults = AIDefaults()
            textModels = []
            visionModels = []
            audioModels = []
            videoModels = []
            errorMessage = nil
        } catch {
            logger.error("Failed to reset AI defaults: \(error.localizedDescription)")
            errorMessage = "Failed to reset: \(error.localizedDescription)"
        }
    }
}
