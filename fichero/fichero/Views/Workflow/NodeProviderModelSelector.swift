import OSLog
import SwiftUI

private let logger = Logger(subsystem: "com.fichero.fichero", category: "NodeProviderModelSelector")

/// Sentinel provider ID for Apple Vision (on-device OCR)
let appleVisionProviderId = "apple_vision"

/// Provider and model selection component for workflow nodes
struct NodeProviderModelSelector: View {
    @Binding var node: WorkflowNode
    @Binding var selectedProviderId: String
    @Binding var selectedModelId: String
    @Binding var isLoadingProviders: Bool

    let providers: [LLMProvider]
    let toolRequiresVision: Bool
    /// Whether this tool supports Apple Vision as a provider option
    let toolSupportsAppleVision: Bool
    let onLoadProviders: () async -> Void

    /// Whether Apple Vision is currently selected
    private var isAppleVisionSelected: Bool {
        selectedProviderId == appleVisionProviderId
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            // Provider picker
            VStack(alignment: .leading, spacing: 4) {
                Text("Provider")
                    .font(.caption)
                    .foregroundColor(.secondary)

                if isLoadingProviders {
                    ProgressView()
                        .frame(maxWidth: .infinity, alignment: .leading)
                } else if providers.isEmpty && !toolSupportsAppleVision {
                    Text("No providers configured")
                        .font(.caption)
                        .foregroundColor(.orange)
                } else {
                    providerPicker
                }
            }

            // Model picker (hidden when Apple Vision is selected)
            if !isAppleVisionSelected {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Model")
                        .font(.caption)
                        .foregroundColor(.secondary)

                    modelPicker
                }
            }
        }
    }

    private var providerPicker: some View {
        let availableProviders = providers.filter { provider in
            guard provider.available else { return false }
            if toolRequiresVision {
                return provider.supportsVision
            }
            return true
        }

        return Group {
            if availableProviders.isEmpty && !toolSupportsAppleVision {
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

                    // Apple Vision as first option for tools that support it
                    if toolSupportsAppleVision {
                        Label("Apple Vision (On-Device)", systemImage: "apple.logo")
                            .tag(appleVisionProviderId)
                    }

                    ForEach(availableProviders) { provider in
                        Text(provider.name).tag(provider.id)
                    }
                }
                .pickerStyle(.menu)
                .onChange(of: selectedProviderId) { _, newValue in
                    guard !newValue.isEmpty else { return }

                    if newValue == appleVisionProviderId {
                        // Apple Vision selected — set vision_mode, clear LLM provider/model
                        if node.config == nil { node.config = [:] }
                        node.config?["vision_mode"] = .string("apple")
                        node.providerName = nil
                        node.modelName = nil
                        node.usesLLM = false
                        selectedModelId = ""
                        logger.info("Apple Vision selected for node \(node.id)")
                    } else {
                        // LLM provider selected
                        if node.config == nil { node.config = [:] }
                        node.config?["vision_mode"] = .string("llm")
                        node.providerName = newValue
                        node.usesLLM = true
                        logger.info("Provider selected: id=\(newValue)")
                        if let provider = providers.first(where: { $0.id == newValue }),
                           let firstModel = provider.models.first {
                            selectedModelId = firstModel
                            node.modelName = firstModel
                        }
                    }
                }
            }
        }
    }

    private var modelPicker: some View {
        let selectedProvider = providers.first { $0.id == selectedProviderId }
        let models = selectedProvider?.models ?? []

        return Group {
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
                    logger.info("Model selected: \(newValue)")
                }
            }
        }
    }
}
