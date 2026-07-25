import OSLog
import SwiftUI

private let logger = Logger(subsystem: "app.fichero.fichero", category: "NodeProviderModelSelector")

/// Sentinel provider ID for Apple Vision (on-device OCR)
let appleVisionProviderId = "apple_vision"

/// Capability-tier model aliases (#810/#814). When selected, the node's
/// providerName is persisted as the literal string "$small" or "$large";
/// the workflow runtime's resolve_model_alias() looks up the concrete
/// provider+model from the user's AIDefaults at execution time.
let smallAliasProviderId = "$small"
let largeAliasProviderId = "$large"

/// Provider and model selection component for workflow nodes
struct NodeProviderModelSelector: View {
    struct ProviderOption: Identifiable, Hashable {
        let id: String
        let name: String
        let providerType: String
        let available: Bool
        let supportsVision: Bool
        let models: [String]
    }

    @Binding var node: WorkflowNode
    @Binding var selectedProviderId: String
    @Binding var selectedModelId: String
    @Binding var isLoadingProviders: Bool

    let providers: [ProviderOption]
    let toolRequiresVision: Bool
    /// Whether this tool supports Apple Vision as a provider option
    let toolSupportsAppleVision: Bool
    let onLoadProviders: () async -> Void

    /// Whether Apple Vision is currently selected
    private var isAppleVisionSelected: Bool {
        selectedProviderId == appleVisionProviderId
    }

    /// Whether a $small / $large alias is currently selected — model
    /// picker hides when so, the runtime resolver fills both fields.
    private var isAliasSelected: Bool {
        selectedProviderId == smallAliasProviderId
            || selectedProviderId == largeAliasProviderId
    }

    /// Whether no explicit provider is set — node uses the workflow/system default.
    private var isDefaultSelected: Bool {
        selectedProviderId.isEmpty
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

            // Model picker hidden when Default / Apple Vision / tier alias —
            // runtime fills both fields in all three cases.
            if !isDefaultSelected && !isAppleVisionSelected && !isAliasSelected {
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
            // Hide the catalog Apple Intelligence row when the tool offers
            // explicit Apple Vision, to avoid duplicate Apple choices. Uses
            // typed providerType instead of brittle name matching (#768).
            if toolSupportsAppleVision {
                if provider.providerType == "apple" {
                    return false
                }
            }
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
                    Text("Default").tag("")

                    // Apple Vision as first option for tools that support it
                    if toolSupportsAppleVision {
                        Label("Apple Vision (On-Device)", systemImage: "apple.logo")
                            .tag(appleVisionProviderId)
                    }

                    // $small / $large aliases (#810/#814). Selecting an
                    // alias persists provider="$small"/"$large" and the
                    // workflow runtime resolves to the user's configured
                    // Default Small / Default Large model from Settings.
                    Label("$small (default small model)", systemImage: "leaf")
                        .tag(smallAliasProviderId)
                    Label("$large (default large model)", systemImage: "sparkles")
                        .tag(largeAliasProviderId)

                    ForEach(availableProviders) { provider in
                        Text(provider.name).tag(provider.id)
                    }
                }
                .pickerStyle(.menu)
                .onChange(of: selectedProviderId) { _, newValue in
                    if newValue.isEmpty {
                        // Default selected — clear explicit provider/model so the runtime uses its default
                        node.config?.removeValue(forKey: "vision_mode")
                        node.providerName = nil
                        node.modelName = nil
                        node.usesLLM = false
                        selectedModelId = ""
                        return
                    }

                    if newValue == appleVisionProviderId {
                        // Apple Vision selected — set vision_mode, clear LLM provider/model
                        if node.config == nil { node.config = [:] }
                        node.config?["vision_mode"] = .string("apple")
                        node.providerName = nil
                        node.modelName = nil
                        node.usesLLM = false
                        selectedModelId = ""
                        logger.info("Apple Vision selected for node \(node.id)")
                    } else if newValue == smallAliasProviderId
                                || newValue == largeAliasProviderId {
                        // Tier alias — runtime fills provider+model. Model
                        // picker is hidden via isAliasSelected.
                        node.config?.removeValue(forKey: "vision_mode")
                        node.providerName = newValue
                        node.modelName = nil
                        node.usesLLM = true
                        selectedModelId = ""
                        logger.info(
                            "Alias \(newValue) selected for node \(node.id)"
                        )
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
