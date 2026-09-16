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
                // The USER-CONFIGURED models for this provider — exactly the list
                // AI Settings shows, under the same labels, via the one shared
                // mapping (spec `nodeconfig.model.same-list-as-settings`, Daniel
                // 2026-09-08). The catalog used to be offered here, which let a
                // node pick a model the provider's API does not serve → 404 at run.
                let rows = try await providerService.listProviderModels(providerId: provider.id)
                let modelChoices = ModelPicker.ModelChoice.configured(rows)
                // Vision capability from the configured rows, with Settings'
                // family-floor fallback for legacy rows saved without caps —
                // an Opus/Gemini row must not hide its provider from a vision tool.
                let supportsVision = rows.contains {
                    $0.capabilities.contains("vision")
                        || ($0.capabilities.isEmpty
                            && AISettingsView.TierCapability.idLooksVisionCapable($0.modelId))
                }
                loaded.append(
                    NodeProviderModelSelector.ProviderOption(
                        id: provider.id,
                        name: provider.name,
                        providerType: provider.providerType,
                        available: true,
                        supportsVision: supportsVision,
                        models: modelChoices
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
                    selectedModelId = node.modelName ?? provider.models.first?.id ?? ""
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
                    // Also move the picker's own selection, or the chip keeps showing the OLD model
                    // until the popover is reopened (spec nodeconfig.compare.apply-updates-picker,
                    // F13 — applying a comparison result looked like it did nothing).
                    selectedProviderId = provider
                    selectedModelId = model
                }
            )
        }
    }
}
