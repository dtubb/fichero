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

extension WorkflowNode {
    mutating func applyProviderSelection(
        providerId: String,
        providers: [NodeProviderModelSelector.ProviderOption],
        toolRequiresVision: Bool,
        toolSupportsAppleVision: Bool
    ) -> String {
        let isVisionTool = toolRequiresVision || toolSupportsAppleVision
        if providerId.isEmpty {
            applyDefaultProviderSelection(clearVisionMode: toolSupportsAppleVision)
            return ""
        }

        if providerId == appleVisionProviderId {
            applyAppleVisionProviderSelection()
            return ""
        }

        if providerId == smallAliasProviderId || providerId == largeAliasProviderId {
            applyAliasProviderSelection(providerId, isVisionTool: isVisionTool)
            return ""
        }

        return applyLLMProviderSelection(
            providerId,
            providers: providers,
            isVisionTool: isVisionTool
        )
    }

    private mutating func applyDefaultProviderSelection(clearVisionMode: Bool) {
        providerName = nil
        modelName = nil
        usesLLM = false
        if clearVisionMode {
            config?.removeValue(forKey: "vision_mode")
            if config?.isEmpty == true {
                config = nil
            }
        }
    }

    private mutating func applyAppleVisionProviderSelection() {
        if config == nil { config = [:] }
        config?["vision_mode"] = .string("apple")
        providerName = nil
        modelName = nil
        usesLLM = false
    }

    private mutating func applyAliasProviderSelection(
        _ providerId: String,
        isVisionTool: Bool
    ) {
        if isVisionTool {
            if config == nil { config = [:] }
            config?["vision_mode"] = .string("llm")
        }
        providerName = providerId
        modelName = nil
        usesLLM = true
    }

    private mutating func applyLLMProviderSelection(
        _ providerId: String,
        providers: [NodeProviderModelSelector.ProviderOption],
        isVisionTool: Bool
    ) -> String {
        if isVisionTool {
            if config == nil { config = [:] }
            config?["vision_mode"] = .string("llm")
        }
        providerName = providerId
        usesLLM = true
        guard let provider = providers.first(where: { $0.id == providerId }),
              let firstModel = provider.models.first else {
            return ""
        }
        modelName = firstModel
        return firstModel
    }
}

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
                    selectedModelId = node.applyProviderSelection(
                        providerId: newValue,
                        providers: providers,
                        toolRequiresVision: toolRequiresVision,
                        toolSupportsAppleVision: toolSupportsAppleVision
                    )

                    if newValue == appleVisionProviderId {
                        logger.info("Apple Vision selected for node \(node.id)")
                    } else if newValue == smallAliasProviderId
                                || newValue == largeAliasProviderId {
                        logger.info(
                            "Alias \(newValue) selected for node \(node.id)"
                        )
                    } else if !newValue.isEmpty {
                        logger.info("Provider selected: id=\(newValue)")
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
