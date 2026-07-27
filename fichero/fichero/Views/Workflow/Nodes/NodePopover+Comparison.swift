import OSLog
import SwiftUI

private let comparisonLogger = Logger(subsystem: "app.fichero.fichero", category: "NodePopover")

// MARK: - Provider loading + Compare Models affordance for NodePopover

extension NodePopover {
    func loadProviders() async {
        guard !isLoadingProviders else { return }
        isLoadingProviders = true
        defer { isLoadingProviders = false }

        do {
            let configured = try await providerService.listProviders()
            var loaded: [NodeProviderModelSelector.ProviderOption] = []
            for provider in configured where provider.enabled {
                let modelInfos = try await providerService.listAvailableModels(
                    providerType: provider.providerType
                )
                let modelIds = modelInfos.map(\.modelId)
                let supportsVision = modelInfos.contains { $0.supportsVision }
                loaded.append(
                    NodeProviderModelSelector.ProviderOption(
                        id: provider.id,
                        name: provider.name,
                        providerType: provider.providerType,
                        available: true,
                        supportsVision: supportsVision,
                        models: modelIds
                    )
                )
            }
            providers = loaded
            comparisonLogger.info(
                "Loaded \(providers.count) providers, \(providers.filter { $0.available }.count) available"
            )

            if let providerId = configuredNodeProviderId(node) {
                if isModelAliasProviderId(providerId) {
                    selectedProviderId = providerId
                    selectedModelId = ""
                } else if let provider = providers.first(where: { $0.id == providerId }) {
                    selectedProviderId = provider.id
                    selectedModelId = node.modelName ?? provider.models.first ?? ""
                }
            }
        } catch {
            comparisonLogger.error("Failed to load providers: \(String(describing: error))")
        }
    }

    /// "Compare Models…" button + sheet, extracted to keep NodePopover under length limits.
    var compareModelsButton: some View {
        Button {
            showingNodeComparison = true
        } label: {
            Label("Compare Models…", systemImage: "square.split.2x2")
                .font(.caption)
                .frame(maxWidth: .infinity)
        }
        .buttonStyle(.bordered)
        .sheet(isPresented: $showingNodeComparison) {
            NodeComparisonSheet(
                workflowId: workflowId,
                node: node,
                onApply: { provider, model in
                    node.providerName = provider
                    node.modelName = model
                    node.usesLLM = true
                }
            )
        }
    }
}
