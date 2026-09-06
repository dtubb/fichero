import SwiftUI

/// Sentinel provider ID for Apple Vision (on-device OCR).
let appleVisionProviderId = "apple_vision"

/// Capability-tier model aliases (#810/#814). When selected, the node's
/// providerName is persisted as the literal alias; the workflow runtime's
/// resolve_model_alias() looks up the concrete provider+model from the user's
/// AIDefaults at execution time.
let smallAliasProviderId = "$small"
let largeAliasProviderId = "$large"
let visionSmallAliasProviderId = "$vision_small"
let visionMediumAliasProviderId = "$vision_medium"
let visionLargeAliasProviderId = "$vision_large"

func isModelAliasProviderId(_ providerId: String) -> Bool {
    [
        smallAliasProviderId,
        largeAliasProviderId,
        visionSmallAliasProviderId,
        visionMediumAliasProviderId,
        visionLargeAliasProviderId
    ].contains(providerId)
}

/// The one provider+model picker, used everywhere a model is chosen — the node
/// popover, AI Settings, and the workflow bar (Daniel, 2026-09-06: "reuse the
/// node popover … it's better than what we have in settings … and workflow bar").
///
/// PURE UI over bindings: it renders the Provider and Model menus (with the
/// first-class "Default", "Apple Vision", and capability-alias entries the node
/// popover pioneered) and writes ONLY `selectedProviderId` / `selectedModelId`.
/// Every side effect — persisting a node's provider/model, pinning a workflow
/// step, saving an AIDefaults tier — stays at the CALL SITE via `.onChange` on
/// the bindings it owns. That separation is what lets the same view drive three
/// surfaces without any of them leaking into it, and keeps pin==runs the call
/// site's own guarantee.
struct ModelPicker: View {
    struct ProviderOption: Identifiable, Hashable {
        let id: String
        let name: String
        /// Carried alongside `id` because AI Settings keys defaults by
        /// providerType while nodes/bar key by provider id.
        let providerType: String
        let available: Bool
        let supportsVision: Bool
        let models: [ModelChoice]
    }

    /// One selectable model: `id` is the wire value written to the binding,
    /// `name` its label. The node popover sets name==id (raw model id, as it
    /// always showed); AI Settings sets name to the model's fullName.
    struct ModelChoice: Identifiable, Hashable {
        let id: String
        let name: String
    }

    let providers: [ProviderOption]
    @Binding var selectedProviderId: String
    @Binding var selectedModelId: String

    var isLoading: Bool = false
    /// Show the "Default" (unset) provider entry with tag "".
    var showDefault: Bool = true
    /// Label for the Default entry (settings may prefer "None").
    var defaultLabel: String = "Default"
    /// Show the capability-tier aliases ($small/$large, +vision when required).
    var showAliases: Bool = false
    /// Show the "Apple Vision (On-Device)" provider entry.
    var showAppleVision: Bool = false
    /// Vision-only tool: filter providers to vision-capable + show vision aliases.
    var requiresVision: Bool = false

    private var isAppleVisionSelected: Bool { selectedProviderId == appleVisionProviderId }
    private var isAliasSelected: Bool { isModelAliasProviderId(selectedProviderId) }
    private var isDefaultSelected: Bool { selectedProviderId.isEmpty }

    /// Model picker hides when Default / Apple Vision / tier alias is chosen —
    /// in all three the runtime fills the model, so there is nothing to pick.
    private var showsModelPicker: Bool {
        !isDefaultSelected && !isAppleVisionSelected && !isAliasSelected
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                Text("Provider")
                    .font(.caption)
                    .foregroundColor(.secondary)

                if isLoading {
                    ProgressView()
                        .frame(maxWidth: .infinity, alignment: .leading)
                } else if providers.isEmpty && !showAppleVision {
                    Text("No providers configured")
                        .font(.caption)
                        .foregroundColor(.orange)
                } else {
                    providerPicker
                }
            }

            if showsModelPicker {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Model")
                        .font(.caption)
                        .foregroundColor(.secondary)

                    modelPicker
                }
            }
        }
    }

    private var availableProviders: [ProviderOption] {
        providers.filter { provider in
            guard provider.available else { return false }
            // Hide the catalog Apple Intelligence row when the tool offers
            // explicit Apple Vision, to avoid duplicate Apple choices. Uses
            // typed providerType instead of brittle name matching (#768).
            if showAppleVision, provider.providerType == "apple" {
                return false
            }
            if requiresVision {
                return provider.supportsVision
            }
            return true
        }
    }

    @ViewBuilder
    private var providerPicker: some View {
        if availableProviders.isEmpty && !showAppleVision {
            if requiresVision {
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
                if showDefault {
                    Text(defaultLabel).tag("")
                }

                if showAppleVision {
                    Label("Apple Vision (On-Device)", systemImage: "apple.logo")
                        .tag(appleVisionProviderId)
                }

                if showAliases {
                    // Selecting an alias persists it as the provider; the
                    // workflow runtime resolves it to the user's configured
                    // Default Small / Large model from Settings (#810/#814).
                    Label("$small (default small model)", systemImage: "leaf")
                        .tag(smallAliasProviderId)
                    Label("$large (default large model)", systemImage: "sparkles")
                        .tag(largeAliasProviderId)
                    if requiresVision {
                        Label("$vision_small (default small vision model)", systemImage: "eye")
                            .tag(visionSmallAliasProviderId)
                        Label("$vision_medium (default vision model)", systemImage: "eye.circle")
                            .tag(visionMediumAliasProviderId)
                        Label("$vision_large (default large vision model)", systemImage: "eye.fill")
                            .tag(visionLargeAliasProviderId)
                    }
                }

                ForEach(availableProviders) { provider in
                    Text(provider.name).tag(provider.id)
                }
            }
            .pickerStyle(.menu)
        }
    }

    @ViewBuilder
    private var modelPicker: some View {
        let selectedProvider = providers.first { $0.id == selectedProviderId }
        let models = selectedProvider?.models ?? []

        if models.isEmpty {
            Text("Select a provider first")
                .font(.caption)
                .foregroundColor(.secondary)
        } else {
            Picker("Model", selection: $selectedModelId) {
                Text("Select model...").tag("")
                ForEach(models) { model in
                    Text(model.name).tag(model.id)
                }
            }
            .pickerStyle(.menu)
        }
    }
}

// MARK: - Preview

private struct ModelPickerPreviewHost: View {
    @State private var providerId = ""
    @State private var modelId = ""

    private let providers: [ModelPicker.ProviderOption] = [
        .init(id: "openai", name: "OpenAI", providerType: "openai", available: true, supportsVision: true,
              models: [.init(id: "gpt-4o", name: "GPT-4o"), .init(id: "gpt-4o-mini", name: "GPT-4o mini")]),
        .init(id: "local-omlx", name: "MLX (Local)", providerType: "omlx", available: true, supportsVision: true,
              models: [.init(id: "qwen2.5-vl-7b", name: "qwen2.5-vl-7b"), .init(id: "llama-3.2-3b", name: "llama-3.2-3b")])
    ]

    var body: some View {
        Form {
            Section("Node popover flags (Default + aliases + Apple Vision)") {
                ModelPicker(
                    providers: providers,
                    selectedProviderId: $providerId,
                    selectedModelId: $modelId,
                    showDefault: true,
                    showAliases: true,
                    showAppleVision: true
                )
            }
        }
        .formStyle(.grouped)
        .frame(width: 360)
    }
}

#Preview("ModelPicker") {
    ModelPickerPreviewHost()
}
