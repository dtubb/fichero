import OSLog
import SwiftUI

private let logger = Logger(subsystem: "com.fichero.fichero", category: "Settings")

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
    // Capability-tier model lists ($small / $large aliases — #810/#813).
    @State private var smallModels: [ModelInfo] = []
    @State private var largeModels: [ModelInfo] = []

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
                // tier:.text filters the dropdown to LLM-shaped models
                // (excludes Apple Vision OCR / Apple Speech). (#940)
                modelPicker(selection: $defaults.textModel, models: textModels, tier: .text)
            }

            Section("Vision") {
                Text("Used by Describe and Analyze tools for image understanding.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                providerPicker(selection: $defaults.visionProvider)
                modelPicker(selection: $defaults.visionModel, models: visionModels, tier: .vision)
            }

            Section("Audio") {
                Text("Used by Transcription tools for speech-to-text.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                providerPicker(selection: $defaults.audioProvider)
                modelPicker(selection: $defaults.audioModel, models: audioModels, tier: .audio)
            }

            if featureManager.isWorkflowToolsVideoEnabled {
                Section("Video") {
                    Text("Used by video analysis tools.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    providerPicker(selection: $defaults.videoProvider)
                    modelPicker(selection: $defaults.videoModel, models: videoModels, tier: .vision)
                }
            }

            // Embeddings section removed: Fichero uses a local fastembed model
            // (BAAI/bge-m3) for semantic search. There's no user-facing choice
            // to make — exposing a picker with Provider=None/Model=None was
            // confusing. (Daniel 2026-04-24)

            // Capability-tier defaults referenced by workflow nodes via the
            // $small / $large aliases (#810/#813). Set Apple Intelligence
            // for $small (private + free local) and a frontier provider
            // (Anthropic / OpenAI / OpenRouter Qwen) for $large to enable
            // the Catalogue (Mixed) preset.
            Section("Default Small Model ($small)") {
                let smallHelp =
                    "Workflow nodes that declare $small resolve to this " +
                    "model — fast / cheap / local. Apple Intelligence is " +
                    "the natural pick (free, private, on-device)."
                Text(smallHelp)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                providerPicker(selection: $defaults.smallProvider)
                modelPicker(selection: $defaults.smallModel, models: smallModels)
            }

            Section("Default Large Model ($large)") {
                let largeHelp =
                    "Workflow nodes that declare $large resolve to this " +
                    "model — used for the catalogue narrative in the Mixed " +
                    "preset. Pick a frontier model (Claude, GPT-4, Qwen 70B+)."
                Text(largeHelp)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                providerPicker(selection: $defaults.largeProvider)
                modelPicker(selection: $defaults.largeModel, models: largeModels)
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
        // Provider-change handlers reset the model AND reload the list
        // for the new provider, then pick its first model as the new
        // default. Pre-fix, switching provider left the stale model
        // selected (which would 404 at runtime) and required
        // tab-away-and-back to refresh the picker. (#936)
        .onChange(of: defaults.textProvider) { _, newValue in
            loadModelsResettingSelection(
                for: newValue, into: $textModels, selecting: $defaults.textModel,
            )
        }
        .onChange(of: defaults.visionProvider) { _, newValue in
            loadModelsResettingSelection(
                for: newValue, into: $visionModels, selecting: $defaults.visionModel,
            )
        }
        .onChange(of: defaults.audioProvider) { _, newValue in
            loadModelsResettingSelection(
                for: newValue, into: $audioModels, selecting: $defaults.audioModel,
            )
        }
        .onChange(of: defaults.videoProvider) { _, newValue in
            loadModelsResettingSelection(
                for: newValue, into: $videoModels, selecting: $defaults.videoModel,
            )
        }
        .onChange(of: defaults.embeddingsProvider) { _, newValue in
            loadModelsResettingSelection(
                for: newValue, into: $embeddingsModels, selecting: $defaults.embeddingsModel,
            )
        }
        .onChange(of: defaults.smallProvider) { _, newValue in
            loadModelsResettingSelection(
                for: newValue, into: $smallModels, selecting: $defaults.smallModel,
            )
        }
        .onChange(of: defaults.largeProvider) { _, newValue in
            loadModelsResettingSelection(
                for: newValue, into: $largeModels, selecting: $defaults.largeModel,
            )
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

        Picker("Provider", selection: selection) {
            Text("None").tag("")
            ForEach(uniqueProviders, id: \.providerType) { provider in
                Text(provider.name).tag(provider.providerType)
            }
        }
    }

    /// Capability requirement for a Defaults tier — used by modelPicker
    /// to filter the dropdown to only models that support the tier's
    /// purpose (Vision tier shows vision models only, Audio shows
    /// audio/transcription only). \\\`text\\\` includes any LLM (everything
    /// that isn't strictly vision-only or audio-only). \\\`any\\\` shows
    /// everything — used for the user-tier \\\`\$small\\\` / \\\`\$large\\\`
    /// pickers where the user picks the cheapest / most-capable for
    /// their workflows regardless of typed capability. (#940)
    enum TierCapability {
        case text
        case vision
        case audio
        case any

        func matches(_ model: ModelInfo) -> Bool {
            switch self {
            case .text:
                // A model is text-capable when it's NOT vision-or-audio
                // only. Most LLMs are; the seeded Apple Vision (OCR)
                // and Apple Speech rows are not.
                return !(model.supportsVision || model.supportsAudioInput)
                    || model.modelId == "apple-intelligence"
            case .vision:
                return model.supportsVision
            case .audio:
                return model.supportsAudioInput
            case .any:
                return true
            }
        }
    }

    @ViewBuilder
    func modelPicker(
        selection: Binding<String>,
        models: [ModelInfo],
        tier: TierCapability = .any,
    ) -> some View {
        let currentSelection = selection.wrappedValue
        let hasCurrentSelection = !currentSelection.isEmpty
        let filtered = models.filter { tier.matches($0) }
        let hasCurrentInList = filtered.contains { $0.modelId == currentSelection }

        Picker("Model", selection: selection) {
            Text("None").tag("")
            if hasCurrentSelection && !hasCurrentInList {
                // Show the saved value even when filtered-out so the
                // user can see "this saved selection doesn't match the
                // tier" instead of a silent reset. They can pick a new
                // compatible one from the dropdown.
                Text("\(currentSelection) (saved — wrong capability)").tag(currentSelection)
            }
            ForEach(filtered, id: \.modelId) { model in
                Text(model.fullName).tag(model.modelId)
            }
        }
    }

    /// Provider-change companion to \\\`loadModels\\\` — clears the model
    /// selection immediately so the picker doesn't briefly show a
    /// stale model for the OLD provider, then loads the new list and
    /// auto-picks its first model. Fixes the two halves of #936:
    /// stale picker after provider change AND requires-tab-cycle to
    /// load. Combined into one helper because the load + reselect are
    /// always tied together — separate \\\`loadModels\\\` stays for the
    /// loadDefaults() initial pass which already knows the right
    /// model from persisted defaults.
    func loadModelsResettingSelection(
        for providerType: String,
        into models: Binding<[ModelInfo]>,
        selecting selection: Binding<String>,
    ) {
        // Clear immediately so the picker drops the stale row.
        selection.wrappedValue = ""

        guard !providerType.isEmpty else {
            models.wrappedValue = []
            return
        }

        guard let provider = appState.providers.first(
            where: { $0.providerType == providerType }
        ) else {
            models.wrappedValue = []
            return
        }

        Task {
            do {
                let configured = try await appState.providerService
                    .listProviderModels(providerId: provider.id)
                let list = configured.map { user in
                    ModelInfo(
                        modelId: user.modelId,
                        fullName: user.name,
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
                        supportsVision: user.capabilities.contains("vision"),
                        supportsFunctionCalling: user.capabilities.contains("tools"),
                        supportsAudioInput: user.capabilities.contains("audio"),
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
                models.wrappedValue = list
                // Auto-pick the first model for the new provider so
                // the picker isn't left on "None" — saves a click on
                // every provider change.
                if let first = list.first {
                    selection.wrappedValue = first.modelId
                }
            } catch {
                logger.error(
                    "Failed to load models for \(providerType): \(error.localizedDescription)"
                )
                models.wrappedValue = []
            }
        }
    }

    func loadModels(for providerType: String, into models: Binding<[ModelInfo]>) {
        guard !providerType.isEmpty else {
            models.wrappedValue = []
            return
        }

        // Show ONLY user-configured models — the ones they've actually added
        // for this provider under Settings → Models. The earlier LiteLLM
        // catalog fallback let users pick model names the provider's API
        // doesn't actually serve, producing runtime 404s (e.g. picking a
        // DashScope model when the provider config routed to HuggingFace).
        // Daniel's UX call: "the user has to think about it" — they should
        // explicitly curate which models work, not rely on a permissive
        // dropdown of every model LiteLLM knows about.
        guard let provider = appState.providers.first(
            where: { $0.providerType == providerType }
        ) else {
            models.wrappedValue = []
            return
        }

        Task {
            do {
                let configured = try await appState.providerService
                    .listProviderModels(providerId: provider.id)
                models.wrappedValue = configured.map { user in
                    ModelInfo(
                        modelId: user.modelId,
                        fullName: user.name,
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
                        supportsVision: user.capabilities.contains("vision"),
                        supportsFunctionCalling: user.capabilities.contains("tools"),
                        supportsAudioInput: user.capabilities.contains("audio"),
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
                logger.error(
                    "Failed to load configured models for \(providerType): \(error.localizedDescription)"
                )
            }
        }
    }

    func loadDefaults() async {
        isLoading = true
        defer { isLoading = false }

        // Refresh providers list so the picker reflects providers added
        // since AppState's last load. Defensive — ProvidersView also calls
        // appState.loadProviders after adding, but a settings sheet may
        // open with a stale list.
        await appState.loadProviders()

        do {
            defaults = try await appState.fetchAIDefaults()

            // First-run convenience: if no defaults are saved AND Apple is
            // available locally, default Text/Vision/Audio to Apple so users
            // don't have to manually pick on a fresh install. They can
            // change to a cloud provider once they've added one.
            if defaults.textProvider.isEmpty
                && defaults.visionProvider.isEmpty
                && defaults.audioProvider.isEmpty,
               appState.providers.contains(where: { $0.providerType == "apple" }) {
                defaults.textProvider = "apple"
                defaults.visionProvider = "apple"
                defaults.audioProvider = "apple"
                // Persist so the user sees the same choice on next launch.
                try? await appState.saveAIDefaults(defaults)
            }

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
            if !defaults.smallProvider.isEmpty {
                loadModels(for: defaults.smallProvider, into: $smallModels)
            }
            if !defaults.largeProvider.isEmpty {
                loadModels(for: defaults.largeProvider, into: $largeModels)
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
            smallModels = []
            largeModels = []
            errorMessage = nil
        } catch {
            logger.error("Failed to reset AI defaults: \(error.localizedDescription)")
            errorMessage = "Failed to reset: \(error.localizedDescription)"
        }
    }
}
