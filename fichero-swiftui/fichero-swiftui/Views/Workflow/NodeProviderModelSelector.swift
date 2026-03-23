import SwiftUI
import OSLog

private let logger = Logger(subsystem: "com.tubb.Fichero", category: "NodeProviderModelSelector")

/// Provider and model selection component for workflow nodes
struct NodeProviderModelSelector: View {
    @Binding var node: WorkflowNode
    @Binding var selectedProviderId: String
    @Binding var selectedModelId: String
    @Binding var isLoadingProviders: Bool

    let providers: [LLMProvider]
    let toolRequiresVision: Bool
    let onLoadProviders: () async -> Void

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
                } else if providers.isEmpty {
                    Text("No providers configured")
                        .font(.caption)
                        .foregroundColor(.orange)
                } else {
                    providerPicker
                }
            }

            // Model picker
            VStack(alignment: .leading, spacing: 4) {
                Text("Model")
                    .font(.caption)
                    .foregroundColor(.secondary)

                modelPicker
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
            if availableProviders.isEmpty {
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
                    ForEach(availableProviders) { provider in
                        Text(provider.name).tag(provider.id)
                    }
                }
                .pickerStyle(.menu)
                .onChange(of: selectedProviderId) { _, newValue in
                    guard !newValue.isEmpty else { return }
                    // Use provider ID (e.g. "openrouter") not display name (e.g. "OpenRouter")
                    // The backend expects the provider type ID
                    node.providerName = newValue
                    print("[DEBUG] Provider selected: id=\(newValue)")
                    if let provider = providers.first(where: { $0.id == newValue }),
                       let firstModel = provider.models.first {
                        selectedModelId = firstModel
                        node.modelName = firstModel
                        print("[DEBUG] Model set to: \(firstModel)")
                    }
                    print(
                        "[DEBUG] Node after update: providerName=\(node.providerName ?? "nil"), " +
                        "modelName=\(node.modelName ?? "nil")"
                    )
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
                    print("[DEBUG] Model manually selected: \(newValue), node.modelName=\(node.modelName ?? "nil")")
                }
            }
        }
    }
}
