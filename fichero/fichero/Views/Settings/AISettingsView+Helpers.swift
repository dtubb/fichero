import FicheroAPIClient
import OSLog
import SwiftUI

private let settingsLogger = Logger(subsystem: "app.fichero.fichero", category: "Settings")

// MARK: - Model Pickers + Loading

extension AISettingsView {

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
    /// to filter the dropdown to only models whose capability fits the slot.
    /// Matches against the model's capability strings as reported by the
    /// provider/registry; it never hardcodes model ids (#940 / #1290).
    /// A model fits a tier when its capabilities intersect the tier's set:
    ///   - `.text`   → Text / $small / $large (chat/completion LLMs)
    ///   - `.vision` → Vision / Video (image understanding & OCR)
    ///   - `.audio`  → Audio (speech-to-text / transcription)
    ///   - `.any`    → no filtering (fallback)
    enum TierCapability {
        case text
        case vision
        case audio
        case any

        /// Capability strings (lowercased) that satisfy this tier.
        private var acceptedCapabilities: Set<String> {
            switch self {
            case .text: return ["text", "chat", "llm"]
            case .vision: return ["vision", "ocr"]
            case .audio: return ["audio", "transcription"]
            case .any: return []
            }
        }

        func matches(_ model: ModelInfo) -> Bool {
            let accepted = acceptedCapabilities
            if accepted.isEmpty { return true }  // .any

            let caps = Set(model.capabilities.map { $0.lowercased() })
            if !caps.isDisjoint(with: accepted) { return true }

            // Tolerate legacy rows that carry no capability metadata
            // (cloud models added before registry-derived caps, #1290):
            // treat an unknown model as LLM-shaped since chat is the
            // registry default. Vision/Audio require explicit caps so a
            // text model never leaks into those slots.
            if case .text = self { return caps.isEmpty }
            return false
        }
    }

    @ViewBuilder
    func modelPicker(
        selection: Binding<String>,
        models: [ModelInfo],
        tier: TierCapability = .any,
        ) -> some View {
        // Only offer models whose capability fits this slot. A saved
        // value that no longer fits (legacy bad data) is simply not
        // listed, so the Picker shows "None" and the user must re-pick a
        // valid model — a capability mismatch can't be selected or saved.
        // The old "(saved — wrong capability)" escape-hatch row is gone
        // by design (#1290).
        let filtered = models.filter { tier.matches($0) }

        Picker("Model", selection: selection) {
            Text("None").tag("")
            ForEach(filtered, id: \.modelId) { model in
                Text(model.fullName).tag(model.modelId)
            }
        }
    }

    /// Provider-change companion — clears the model selection immediately,
    /// loads the new list, then auto-picks a model. Fixes #936: stale picker
    /// after provider change + requires-tab-cycle to load.
    ///
    /// Race guard (#1344): if the current selection is already valid in the
    /// new list (e.g. restored from a saved default after loadDefaults runs),
    /// we preserve it rather than blindly picking the first item. Only falls
    /// back to first-item auto-pick when the saved model is absent from the
    /// new list or when no model was previously selected.
    func loadModelsResettingSelection(
        for providerType: String,
        into models: Binding<[ModelInfo]>,
        selecting selection: Binding<String>,
        ) {
        let priorSelection = selection.wrappedValue
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
                let list = configuredModelInfos(from: configured, providerType: providerType)
                models.wrappedValue = list
                // Prefer the already-saved selection if it still exists in
                // the new list; fall back to first model otherwise.
                if !priorSelection.isEmpty, list.contains(where: { $0.modelId == priorSelection }) {
                    selection.wrappedValue = priorSelection
                } else if let first = list.first {
                    selection.wrappedValue = first.modelId
                }
            } catch {
                settingsLogger.error(
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
        // for this provider under Settings → Models. The LiteLLM catalog
        // fallback let users pick model names the provider's API doesn't
        // actually serve, producing runtime 404s. Daniel's UX call: "the user
        // has to think about it" — they should explicitly curate which models work.
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
                models.wrappedValue = configuredModelInfos(from: configured, providerType: providerType)
            } catch {
                settingsLogger.error(
                    "Failed to load configured models for \(providerType): \(error.localizedDescription)"
                )
            }
        }
    }

    private func configuredModelInfos(
        from configured: [Components.Schemas.UserModelResponse],
        providerType: String
    ) -> [ModelInfo] {
        configured.map { user in
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
                provider: providerType,
                capabilities: user.capabilities
            )
        }
    }

    // MARK: - Data Actions

    func loadDefaults() async {
        isLoading = true
        defer { isLoading = false }

        // Refresh providers list so the picker reflects providers added
        // since AppState's last load.
        await appState.loadProviders()

        do {
            defaults = try await appState.fetchAIDefaults()

            let appleAvailable = appState.providers.contains(where: { $0.providerType == "apple" })
            let beforeSeed = defaults
            defaults.seedAppleDefaultsIfNeeded(appleAvailable: appleAvailable)
            if defaults != beforeSeed {
                // Surface a seed-persist failure instead of showing values that
                // silently evaporate on next launch (#3222 / prefer-raise-over-
                // silent-fallback). Scoped catch so a save failure doesn't abort
                // loading the model-picker lists below.
                do {
                    try await appState.saveAIDefaults(defaults)
                } catch {
                    settingsLogger.error(
                        "Failed to persist seeded Apple defaults: \(error.localizedDescription)"
                    )
                    errorMessage = "Couldn't save the default AI models: \(error.localizedDescription)"
                }
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
            if !defaults.mediumProvider.isEmpty {
                loadModels(for: defaults.mediumProvider, into: $mediumModels)
            }
            if !defaults.largeProvider.isEmpty {
                loadModels(for: defaults.largeProvider, into: $largeModels)
            }
            if !defaults.visionSmallProvider.isEmpty {
                loadModels(for: defaults.visionSmallProvider, into: $visionSmallModels)
            }
            if !defaults.visionMediumProvider.isEmpty {
                loadModels(for: defaults.visionMediumProvider, into: $visionMediumModels)
            }
            if !defaults.visionLargeProvider.isEmpty {
                loadModels(for: defaults.visionLargeProvider, into: $visionLargeModels)
            }
        } catch {
            settingsLogger.error("Failed to load AI defaults: \(error.localizedDescription)")
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
            settingsLogger.error("Failed to save AI defaults: \(error.localizedDescription)")
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
            mediumModels = []
            largeModels = []
            visionSmallModels = []
            visionMediumModels = []
            visionLargeModels = []
            errorMessage = nil
        } catch {
            settingsLogger.error("Failed to reset AI defaults: \(error.localizedDescription)")
            errorMessage = "Failed to reset: \(error.localizedDescription)"
        }
    }
}
