import SwiftUI

// MARK: - Defaults + Advanced Tab Views

extension AISettingsView {

    @ViewBuilder
    var defaultsTab: some View {
        Form {
            Section("Language") {
                Text("Force extraction into one language regardless of the source's own language. Auto detects per source.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Picker("Primary Language", selection: $store.defaults.primaryLanguage) {
                    Text("Auto (detect per source)").tag("")
                    Text("English").tag("en")
                    Text("Spanish").tag("es")
                    Text("French").tag("fr")
                    Text("German").tag("de")
                    Text("Portuguese").tag("pt")
                    Text("Italian").tag("it")
                }
            }

            Section("Text") {
                Text("Used by Summarize, Extract, and Classify tools.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                providerPicker(selection: $store.defaults.textProvider)
                // tier:.text filters the dropdown to LLM-shaped models
                // (excludes Apple Vision OCR / Apple Speech). (#940)
                modelPicker(selection: $store.defaults.textModel, models: textModels, tier: .text)
            }

            Section("Vision") {
                Text("Used by Describe and Analyze tools for image understanding.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                providerPicker(selection: $store.defaults.visionProvider)
                modelPicker(selection: $store.defaults.visionModel, models: visionModels, tier: .vision)
            }

            Section("Audio") {
                Text("Used by Transcription tools for speech-to-text.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                providerPicker(selection: $store.defaults.audioProvider)
                modelPicker(selection: $store.defaults.audioModel, models: audioModels, tier: .audio)
            }

            if featureManager.isWorkflowToolsVideoEnabled {
                Section("Video") {
                    Text("Used by video analysis tools.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    providerPicker(selection: $store.defaults.videoProvider)
                    modelPicker(selection: $store.defaults.videoModel, models: videoModels, tier: .vision)
                }
            }

            // Capability-tier defaults referenced by workflow nodes via the
            // $small / $medium / $large aliases (#810/#813).
            Section("Default Small Model ($small)") {
                let smallHelp =
                    "Workflow nodes that declare $small resolve to this " +
                    "model — fast / cheap / local. Apple Intelligence is " +
                    "the natural pick (free, private, on-device)."
                Text(smallHelp)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                providerPicker(selection: $store.defaults.smallProvider)
                // $small resolves a chat/completion LLM — filter to the
                // text tier so OCR / transcription models can't be picked. (#1290)
                modelPicker(selection: $store.defaults.smallModel, models: smallModels, tier: .text)
            }

            Section("Default Medium Model ($medium)") {
                let mediumHelp =
                    "Workflow nodes that declare $medium resolve to this " +
                    "model — balanced speed and quality for everyday drafting " +
                    "and extraction."
                Text(mediumHelp)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                providerPicker(selection: $store.defaults.mediumProvider)
                modelPicker(selection: $store.defaults.mediumModel, models: mediumModels, tier: .text)
            }

            Section("Default Large Model ($large)") {
                let largeHelp =
                    "Workflow nodes that declare $large resolve to this " +
                    "model — used for the catalogue narrative in the Mixed " +
                    "preset. Pick a frontier model (Claude, GPT-4, Qwen 70B+)."
                Text(largeHelp)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                providerPicker(selection: $store.defaults.largeProvider)
                // $large resolves a frontier chat LLM — filter to the
                // text tier so OCR / transcription models can't be picked. (#1290)
                modelPicker(selection: $store.defaults.largeModel, models: largeModels, tier: .text)
            }

            Section("Vision Small Model ($vision_small)") {
                Text("Vision workflow nodes that declare $vision_small resolve to this fast image model.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                providerPicker(selection: $store.defaults.visionSmallProvider)
                modelPicker(selection: $store.defaults.visionSmallModel, models: visionSmallModels, tier: .vision)
            }

            Section("Vision Medium Model ($vision_medium)") {
                Text("Vision workflow nodes that declare $vision_medium resolve to this balanced image model.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                providerPicker(selection: $store.defaults.visionMediumProvider)
                modelPicker(selection: $store.defaults.visionMediumModel, models: visionMediumModels, tier: .vision)
            }

            Section("Vision Large Model ($vision_large)") {
                Text("Vision workflow nodes that declare $vision_large resolve to this frontier image model.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                providerPicker(selection: $store.defaults.visionLargeProvider)
                modelPicker(selection: $store.defaults.visionLargeModel, models: visionLargeModels, tier: .vision)
            }

            Section {
                Label(
                    "Per-tool overrides in the workflow editor take precedence.",
                    systemImage: "info.circle"
                )
                .font(.caption)
                .foregroundStyle(.secondary)

                Button("Reset All Defaults", role: .destructive) {
                    Task { await resetAll() }
                }
            }
        }
        .formStyle(.grouped)
        // Provider-change handlers reset the model AND reload the list
        // for the new provider, then pick its first model as the new
        // default. Pre-fix, switching provider left the stale model
        // selected (which would 404 at runtime) and required
        // tab-away-and-back to refresh the picker. (#936)
        .onChange(of: store.defaults.textProvider) { _, newValue in
            loadModelsResettingSelection(
                for: newValue, into: $textModels, selecting: $store.defaults.textModel,
                )
        }
        .onChange(of: store.defaults.visionProvider) { _, newValue in
            loadModelsResettingSelection(
                for: newValue, into: $visionModels, selecting: $store.defaults.visionModel,
                )
        }
        .onChange(of: store.defaults.audioProvider) { _, newValue in
            loadModelsResettingSelection(
                for: newValue, into: $audioModels, selecting: $store.defaults.audioModel,
                )
        }
        .onChange(of: store.defaults.videoProvider) { _, newValue in
            loadModelsResettingSelection(
                for: newValue, into: $videoModels, selecting: $store.defaults.videoModel,
                )
        }
        .onChange(of: store.defaults.embeddingsProvider) { _, newValue in
            loadModelsResettingSelection(
                for: newValue, into: $embeddingsModels, selecting: $store.defaults.embeddingsModel,
                )
        }
        .onChange(of: store.defaults.smallProvider) { _, newValue in
            loadModelsResettingSelection(
                for: newValue, into: $smallModels, selecting: $store.defaults.smallModel,
                )
        }
        .onChange(of: store.defaults.mediumProvider) { _, newValue in
            loadModelsResettingSelection(
                for: newValue, into: $mediumModels, selecting: $store.defaults.mediumModel,
                )
        }
        .onChange(of: store.defaults.largeProvider) { _, newValue in
            loadModelsResettingSelection(
                for: newValue, into: $largeModels, selecting: $store.defaults.largeModel,
                )
        }
        .onChange(of: store.defaults.visionSmallProvider) { _, newValue in
            loadModelsResettingSelection(
                for: newValue, into: $visionSmallModels, selecting: $store.defaults.visionSmallModel,
                )
        }
        .onChange(of: store.defaults.visionMediumProvider) { _, newValue in
            loadModelsResettingSelection(
                for: newValue, into: $visionMediumModels, selecting: $store.defaults.visionMediumModel,
                )
        }
        .onChange(of: store.defaults.visionLargeProvider) { _, newValue in
            loadModelsResettingSelection(
                for: newValue, into: $visionLargeModels, selecting: $store.defaults.visionLargeModel,
                )
        }
    }

    @ViewBuilder
    var providersTab: some View {
        ProvidersView()
            .environment(appState.providerService)
            .environment(appState.modelService)
    }

    @ViewBuilder
    var downloadsTab: some View {
        LocalModelsSettingsView()
    }

    @ViewBuilder
    var localLLMTab: some View {
        LocalInferenceSettingsView(store: appState.localInferenceStore)
    }

    @ViewBuilder
    var advancedTab: some View {
        Form {
            Section("Generation") {
                HStack {
                    Text("Temperature")
                    Slider(value: temperatureBinding, in: 0...2, step: 0.1)
                    Text(temperatureDisplay)
                        .monospacedDigit()
                        .frame(width: 30)
                }
                TextField("Max Tokens", text: $store.defaults.maxTokens)
                    .textFieldStyle(.roundedBorder)
            }

            Section("Prompt") {
                TextField("Prompt Prefix (prepended to all prompts)", text: $store.defaults.promptPrefix, axis: .vertical)
                    .lineLimit(3...6)
            }
        }
        .formStyle(.grouped)
    }
}
