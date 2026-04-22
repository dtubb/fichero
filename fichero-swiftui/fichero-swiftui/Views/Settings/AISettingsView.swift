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
    @State private var embeddingsModels: [ModelInfo] = []

    var body: some View {
        VStack(spacing: 0) {
            if !appState.isBackendRunning {
                Form {
                    Section {
                        Label("Backend not connected", systemImage: "exclamationmark.triangle")
                            .foregroundStyle(.secondary)
                    }
                }
                .formStyle(.grouped)
            } else if isLoading {
                Form {
                    Section {
                        ProgressView("Loading defaults...")
                    }
                }
                .formStyle(.grouped)
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
        Form {
            Section("Text") {
                Text("Used by Summarize, Extract, and Classify tools.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                providerPicker(selection: $defaults.textProvider)
                modelPicker(selection: $defaults.textModel, models: textModels)
            }

            Section("Vision") {
                Text("Used by Describe and Analyze tools for image understanding.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                providerPicker(selection: $defaults.visionProvider)
                modelPicker(selection: $defaults.visionModel, models: visionModels)
            }

            if featureManager.isWorkflowToolsAudioEnabled {
                Section("Audio") {
                    Text("Used by Transcription tools for speech-to-text.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    providerPicker(selection: $defaults.audioProvider)
                    modelPicker(selection: $defaults.audioModel, models: audioModels)
                }
            }

            if featureManager.isWorkflowToolsVideoEnabled {
                Section("Video") {
                    Text("Used by video analysis tools.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    providerPicker(selection: $defaults.videoProvider)
                    modelPicker(selection: $defaults.videoModel, models: videoModels)
                }
            }

            Section("Embeddings") {
                Text("Used by Search to embed and index documents.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                providerPicker(selection: $defaults.embeddingsProvider)
                modelPicker(selection: $defaults.embeddingsModel, models: embeddingsModels)
            }

            Section {
                Label(
                    "Per-tool overrides in the workflow editor take precedence.",
                    systemImage: "info.circle"
                )
                .font(.caption)
                .foregroundStyle(.secondary)

                Button("Reset All Defaults", role: .destructive) {
                    Task { await resetDefaults() }
                }
            }
        }
        .formStyle(.grouped)
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
        .onChange(of: defaults.embeddingsProvider) { _, newValue in
            loadModels(for: newValue, into: $embeddingsModels)
        }
    }

    // MARK: - Advanced Tab

    @ViewBuilder
    private var advancedTab: some View {
        Form {
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
        .formStyle(.grouped)
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
        // De-duplicate by providerType so the Picker ForEach has unique IDs
        // even if the backend returns multiple provider rows with the same type.
        let uniqueProviders = Array(
            Dictionary(grouping: appState.providers, by: { $0.providerType })
                .compactMapValues { $0.first }
                .values
        ).sorted(by: { $0.name < $1.name })

        return Picker("Provider", selection: selection) {
            Text("None").tag("")
            ForEach(uniqueProviders, id: \.providerType) { provider in
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
            if !defaults.embeddingsProvider.isEmpty {
                loadModels(for: defaults.embeddingsProvider, into: $embeddingsModels)
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
            embeddingsModels = []
            errorMessage = nil
        } catch {
            logger.error("Failed to reset AI defaults: \(error.localizedDescription)")
            errorMessage = "Failed to reset: \(error.localizedDescription)"
        }
    }
}
