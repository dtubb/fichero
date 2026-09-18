import FicheroAPIClient
import OSLog
import SwiftUI

private let settingsLogger = Logger(subsystem: "app.fichero.fichero", category: "Settings")

// MARK: - Model Pickers + Loading

extension AISettingsView {

    var temperatureBinding: Binding<Double> {
        Binding(
            get: { Double(store.defaults.temperature) ?? 0.7 },
            set: { store.defaults.temperature = String(format: "%.1f", $0) }
        )
    }

    var temperatureDisplay: String {
        store.defaults.temperature.isEmpty ? "0.7" : store.defaults.temperature
    }

    /// One Defaults slot's model chooser, on the SHARED picker row so a model in
    /// Settings looks identical to the same model in the document island and the
    /// workflow bar (spec RATIFIED 2026-09-15). This is now ONE step — a single
    /// chip opening a popover of `SharedModelRow`s — replacing the old
    /// Provider→Model two-dropdown drill-down (`ModelPicker`, "Spine B") the
    /// creative director's ruling forbids. The real view lives in
    /// `SettingsSharedModelPicker`; the seam and its two bindings are unchanged,
    /// so the `.onChange` provider handlers in `AISettingsView+Tabs` keep working.
    ///
    /// `models` is the caller's already-loaded list for the selected provider;
    /// it seeds the popover so the current provider's models show before the
    /// full fetch lands. The tier filter and its "N models withheld" help move
    /// into the child unchanged.
    @ViewBuilder
    func settingsModelPicker(
        providerSelection: Binding<String>,
        modelSelection: Binding<String>,
        models: [ModelInfo],
        tier: TierCapability = .any
    ) -> some View {
        SettingsSharedModelPicker(
            appState: appState,
            providerSelection: providerSelection,
            modelSelection: modelSelection,
            tier: tier,
            seedModels: models
        )
    }

    /// Capability requirement for a Defaults tier — used by settingsModelPicker
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

        /// The capability name shown in a greyed row's disabled reason
        /// ("Not marked for text — edit its capabilities in Models &
        /// Providers"). `.any` never disables a row, so it needs no label.
        var displayName: String {
            switch self {
            case .text: return "text"
            case .vision: return "vision"
            case .audio: return "audio"
            case .any: return "any"
            }
        }

        func matches(_ model: ModelInfo) -> Bool {
            let accepted = acceptedCapabilities
            if accepted.isEmpty { return true }  // .any

            let caps = Set(model.capabilities.map { $0.lowercased() })
            if !caps.isDisjoint(with: accepted) { return true }

            // The `supports*` bools the discovery endpoint reports, which the
            // `capabilities` strings are silent about (that field is only
            // populated for a user-configured row). Requiring the strings
            // alone is what made a perfectly vision-capable model
            // unselectable for the Vision tier (Daniel, 2026-09-01: "cannot
            // select a model like Opus or Google").
            switch self {
            case .vision where model.supportsVision: return true
            case .audio where model.supportsAudioInput: return true
            default: break
            }

            // Tolerate legacy rows that carry no capability metadata
            // (cloud models added before registry-derived caps, #1290):
            // treat an unknown model as LLM-shaped since chat is the
            // registry default. A capability-less row is exactly the shape a
            // model NEWER than the vendored registry arrives in, so Vision
            // falls back to the family floor rather than to silence — an
            // absent row is indistinguishable from "this provider ships no
            // such model", which is the lie that started this.
            if case .text = self { return caps.isEmpty }
            if case .vision = self, caps.isEmpty {
                return Self.idLooksVisionCapable(model.modelId)
            }
            return false
        }

        /// Mirror of the engine's `infer_vision_support` family floor
        /// (fichero_server/llm/model_types.py). Duplicated deliberately: the
        /// engine cannot re-derive capabilities for a row already saved with
        /// none, and Settings must not present that row as non-existent.
        static func idLooksVisionCapable(_ modelId: String) -> Bool {
            let id = modelId.lowercased()
            let notVision = ["embed", "tts", "whisper", "moderation", "rerank",
                             "guard", "claude-1", "claude-2", "claude-instant",
                             "gemini-1.0", "-audio", "gemma"]
            if notVision.contains(where: id.contains) { return false }
            let vision = ["claude-", "gemini-", "gpt-4o", "gpt-4.1", "gpt-4-turbo",
                          "gpt-5", "gpt-6", "o1", "o3", "o4", "pixtral", "llava",
                          "-vl-", "-vl:", "vl-", "vision", "grok-3", "grok-4",
                          "internvl", "minicpm-v", "moondream"]
            return vision.contains(where: id.contains)
        }
    }

    /// Provider-change companion — loads the new list, then keeps the prior
    /// selection if it is still valid. Fixes #936: stale picker after
    /// provider change + requires-tab-cycle to load.
    ///
    /// Never blanks or auto-picks (house rule: never substitute a different
    /// choice silently — `prefer-raise-over-silent-fallback`):
    /// - the selection is NOT cleared before the fetch. Blanking it
    ///   synchronously triggers `.onChange(of: store.defaults)` to persist
    ///   model="" as an unserialised save that a slower fetch then raced —
    ///   and if the fetch failed, "" is what stuck, silently losing the
    ///   user's pick.
    /// - on fetch error, the prior selection is left exactly as it was and
    ///   the error is surfaced via `loadError`, instead of the list (and the
    ///   selection) going blank.
    /// - when the saved model is absent from the new list, the selection is
    ///   left AS-IS rather than auto-picked to `list.first` — a silent
    ///   substitution is worse than a picker that shows "not in this
    ///   provider's list" until the user chooses again.
    ///
    /// Race guard (#1344): if the current selection is already valid in the
    /// new list (e.g. restored from a saved default after loadDefaults runs),
    /// it is preserved rather than touched at all.
    ///
    /// Pure and `nonisolated static` so a regression to the old `list.first`
    /// auto-pick (or to blanking on failure) fails a test rather than a user's
    /// saved model. It always returns `current` — the "what should we do
    /// instead" answer is "nothing"; a picker with an absent model shows it as
    /// unrecognised in the current list rather than have it changed for you.
    nonisolated static func selectionAfterModelLoad(
        current: String,
        loadedModels: [ModelInfo]
    ) -> String {
        current
    }

    func loadModelsResettingSelection(
        for providerType: String,
        into models: Binding<[ModelInfo]>,
        selecting selection: Binding<String>,
        loadError: Binding<String?> = .constant(nil)
    ) {
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
                let list = Self.configuredModelInfos(from: configured, providerType: providerType)
                models.wrappedValue = list
                loadError.wrappedValue = nil
                // This writes through `selection` unconditionally, and `selectionAfterModelLoad`
                // always returns `current` back — so on every load this is a SELF-write of the
                // value already there. Reviewed (nit, #4694 follow-up): `selection` ultimately
                // binds into `store.defaults` (an `Equatable` struct, AIDefaults.swift), and
                // `AISettingsView`'s `.onChange(of: store.defaults) { Task { await store.save() } }`
                // gates on inequality — SwiftUI only invokes an `onChange` action when the new
                // value differs from the old one, so writing back the SAME string does not
                // re-trigger the persistence Task. Kept (not deleted) because it's what makes
                // `selectionAfterModelLoad` the SOLE assignment path for `selection` here — the
                // shape `AISettingsSelectionTests.productionCallSiteRoutesOnlyThroughThePureFunction`
                // asserts — rather than an unused pure function nothing actually applies.
                selection.wrappedValue = Self.selectionAfterModelLoad(
                    current: selection.wrappedValue, loadedModels: list
                )
            } catch {
                settingsLogger.error(
                    "Failed to load models for \(providerType): \(error.localizedDescription)"
                )
                loadError.wrappedValue = error.localizedDescription
                // The selection and the previously-loaded list are left as
                // they were — a failed refresh must not erase a working
                // configuration.
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
        // actually serve, producing runtime 404s. The maintainer's UX call: "the user
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
                models.wrappedValue = Self.configuredModelInfos(from: configured, providerType: providerType)
            } catch {
                settingsLogger.error(
                    "Failed to load configured models for \(providerType): \(error.localizedDescription)"
                )
            }
        }
    }

    /// Pure and `nonisolated static` so the node-popover parity test
    /// (`NodeModelListParityTests`) can derive Settings' choices for the same
    /// rows without a view instance. Statics on a View type inherit MainActor
    /// under the macOS 26 SDK; this touches no actor state.
    nonisolated static func configuredModelInfos(
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

    // MARK: - Model-picker lists

    /// Populate the per-tier model-picker lists from the store's loaded defaults.
    /// The defaults load + seed + persistence now lives in `AISettingsStore`; this
    /// only fills the transient picker lists the view owns, reading `store.defaults`.
    /// ponytail: these still call `appState` for the model catalog — moving the
    /// model-list loading into the store is a scoped follow-up to #3222.
    func loadModelLists() async {
        let defaults = store.defaults
        // One (provider, target-list) lane per tier — a loop instead of 11 ifs so a
        // new tier is one line, not another branch.
        let lanes: [(provider: String, models: Binding<[ModelInfo]>)] = [
            (defaults.textProvider, $textModels),
            (defaults.visionProvider, $visionModels),
            (defaults.audioProvider, $audioModels),
            (defaults.videoProvider, $videoModels),
            (defaults.embeddingsProvider, $embeddingsModels),
            (defaults.smallProvider, $smallModels),
            (defaults.mediumProvider, $mediumModels),
            (defaults.largeProvider, $largeModels),
            (defaults.visionSmallProvider, $visionSmallModels),
            (defaults.visionMediumProvider, $visionMediumModels),
            (defaults.visionLargeProvider, $visionLargeModels)
        ]
        for lane in lanes where !lane.provider.isEmpty {
            loadModels(for: lane.provider, into: lane.models)
        }
    }

    /// Reset button handler: the store resets the defaults (and surfaces any
    /// failure honestly), then the view clears its picker lists.
    func resetAll() async {
        await store.reset()
        guard store.errorMessage == nil else { return }
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
    }
}
