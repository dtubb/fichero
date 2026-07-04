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
                Picker("Primary Language", selection: $defaults.primaryLanguage) {
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

            // Capability-tier defaults referenced by workflow nodes via the
            // $small / $large aliases (#810/#813).
            Section("Default Small Model ($small)") {
                let smallHelp =
                    "Workflow nodes that declare $small resolve to this " +
                    "model — fast / cheap / local. Apple Intelligence is " +
                    "the natural pick (free, private, on-device)."
                Text(smallHelp)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                providerPicker(selection: $defaults.smallProvider)
                // $small resolves a chat/completion LLM — filter to the
                // text tier so OCR / transcription models can't be picked. (#1290)
                modelPicker(selection: $defaults.smallModel, models: smallModels, tier: .text)
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
                // $large resolves a frontier chat LLM — filter to the
                // text tier so OCR / transcription models can't be picked. (#1290)
                modelPicker(selection: $defaults.largeModel, models: largeModels, tier: .text)
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

    @ViewBuilder
    var providersTab: some View {
        ProvidersView()
            .environmentObject(appState.providerService)
            .environmentObject(appState.modelService)
    }

    @ViewBuilder
    var downloadsTab: some View {
        LocalModelsSettingsView()
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
