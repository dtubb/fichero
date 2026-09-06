import OSLog
import SwiftUI

private let logger = Logger(subsystem: "app.fichero.fichero", category: "NodeProviderModelSelector")

// The provider-id sentinels (appleVisionProviderId, the $-aliases,
// isModelAliasProviderId) now live on the shared ModelPicker, since the picker
// is what renders those entries. This node-specific reader stays here.

func configuredNodeProviderId(_ node: WorkflowNode) -> String? {
    node.providerName ?? node.config?["provider_name"]?.stringValue
}

/// Provider and model selection for workflow nodes — a thin WRAPPER around the
/// shared `ModelPicker` (the one picker used across the node popover, AI Settings
/// and the workflow bar). The picker is pure UI over the two bindings; this
/// wrapper owns the NODE side effects — mapping a provider/model selection onto
/// `WorkflowNode`'s config/providerName/modelName/usesLLM — via `.onChange`.
struct NodeProviderModelSelector: View {
    /// Kept as an alias so existing call sites (`NodePopover`) that name
    /// `NodeProviderModelSelector.ProviderOption` keep compiling; the type now
    /// lives on the shared `ModelPicker`.
    typealias ProviderOption = ModelPicker.ProviderOption

    @Binding var node: WorkflowNode
    @Binding var selectedProviderId: String
    @Binding var selectedModelId: String
    @Binding var isLoadingProviders: Bool

    let providers: [ProviderOption]
    let toolRequiresVision: Bool
    /// Whether this tool supports Apple Vision as a provider option
    let toolSupportsAppleVision: Bool
    let onLoadProviders: () async -> Void

    var body: some View {
        ModelPicker(
            providers: providers,
            selectedProviderId: $selectedProviderId,
            selectedModelId: $selectedModelId,
            isLoading: isLoadingProviders,
            showDefault: true,
            showAliases: true,
            showAppleVision: toolSupportsAppleVision,
            requiresVision: toolRequiresVision
        )
        // Side effects live here, at the call site — the picker only moves the
        // bindings. This is the exact provider→node mapping that used to sit
        // inside the picker's onChange; behavior is unchanged.
        .onChange(of: selectedProviderId) { _, newValue in
            applyProviderSelection(newValue)
        }
        .onChange(of: selectedModelId) { _, newValue in
            guard !newValue.isEmpty else { return }
            node.modelName = newValue
            logger.info("Model selected: \(newValue)")
        }
    }

    private func applyProviderSelection(_ newValue: String) {
        node.config?.removeValue(forKey: "provider_name")
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
        } else if isModelAliasProviderId(newValue) {
            // Tier alias — runtime fills provider+model. Model picker hides.
            node.config?.removeValue(forKey: "vision_mode")
            node.providerName = newValue
            node.modelName = nil
            node.usesLLM = true
            selectedModelId = ""
            logger.info("Alias \(newValue) selected for node \(node.id)")
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
