import OSLog
import SwiftUI

private let logger = Logger(subsystem: "app.fichero.fichero", category: "NodeProviderModelSelector")

// The provider-id sentinels (appleVisionProviderId, the $-aliases,
// isModelAliasProviderId) now live on the shared ModelPicker, since the picker
// is what renders those entries. This node-specific reader stays here.

func configuredNodeProviderId(_ node: WorkflowNode) -> String? {
    node.providerName ?? node.config?["provider_name"]?.stringValue
}

/// Provider and model selection for workflow nodes — the one-step `SharedModelRow`
/// picker (spec RATIFIED 2026-09-15,
/// docs/contributor_manual/specs/ui/model-selector-consistency.md), replacing the
/// old Provider→Model two-dropdown DRILL-DOWN (`ModelPicker`, "Spine B"). A single
/// chip opens a popover that lists every configured model grouped by provider,
/// each drawn by `SharedModelRow` — the same row Settings, the island and the
/// workflow bar draw. Choosing a row writes BOTH bindings at once (provider then
/// model), and the NODE side effects — mapping a provider/model selection onto
/// `WorkflowNode`'s config/providerName/modelName/usesLLM — still live here in the
/// unchanged `.onChange`/`apply` seam.
///
/// Source parity, not builder parity (the `SettingsSharedModelPicker` precedent):
/// the pure `SharedModelListBuilder` takes `[LLMProvider]` and SHORTENS names,
/// but this view's source is `[ProviderOption]` whose `ModelChoice`s already carry
/// the configured `fullName`-based labels the parity test (`NodeModelListParityTests`)
/// pins — the SAME `listProviderModels` source Settings uses. So only the ROW
/// converges here; each configured `ModelChoice` is re-dressed as the shared
/// `SharedModelChoice`, keeping the labels the drill-down showed.
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
    /// #4883 (`models.role-defaults-always-offered`): the role-default alias
    /// rows, resolved and built by the caller (`NodePopover`, via
    /// `SharedModelListBuilder.roleDefaultAliases`) — this view only renders
    /// them, it does not resolve them (that fetch/logic has ONE home now,
    /// not a second copy here).
    let roleDefaults: [SharedModelChoice]
    let toolRequiresVision: Bool
    /// Whether this tool supports Apple Vision as a provider option
    let toolSupportsAppleVision: Bool
    let onLoadProviders: () async -> Void

    @State private var isPresented = false

    var body: some View {
        Button {
            isPresented.toggle()
        } label: {
            chipLabel
        }
        .buttonStyle(.bordered)
        .popover(isPresented: $isPresented, arrowEdge: .bottom) {
            pickerList
        }
        // Side effects live here, at the call site — the popover only moves the
        // bindings. This is the exact provider→node mapping that used to sit
        // inside the picker's onChange; behavior is unchanged.
        .onChange(of: selectedProviderId) { _, newValue in
            selectedModelId = Self.apply(
                providerId: newValue, to: &node, providers: providers, currentModelId: selectedModelId
            )
        }
        .onChange(of: selectedModelId) { _, newValue in
            guard !newValue.isEmpty else { return }
            node.modelName = newValue
            logger.info("Model selected: \(newValue)")
        }
    }

    // MARK: - Chip

    @ViewBuilder
    private var chipLabel: some View {
        HStack(spacing: 6) {
            if let current = currentModelChoice {
                ModelFamilyMark(model: current.model, provider: current.provider)
                Text(current.displayName)
                    .lineLimit(1)
            } else {
                Text(currentSpecialLabel)
                    .lineLimit(1)
                    .foregroundStyle(selectedProviderId.isEmpty ? .secondary : .primary)
            }
            Spacer(minLength: 4)
            Image(systemName: "chevron.up.chevron.down")
                .imageScale(.small)
                .foregroundStyle(.secondary)
        }
        .frame(minWidth: 220, alignment: .leading)
    }

    // MARK: - Popover list

    @ViewBuilder
    private var pickerList: some View {
        List {
            // Leading one-tap choices: Default, Apple Vision (when the tool
            // offers it) and the capability-tier aliases. These select a provider
            // sentinel with no model; `apply` fills the rest.
            Section {
                specialRow(displayName: "Default", isCurrent: selectedProviderId.isEmpty) {
                    select(provider: "", model: "")
                }
                if toolSupportsAppleVision {
                    specialRow(
                        displayName: "Apple Vision (On-Device)",
                        isCurrent: selectedProviderId == appleVisionProviderId
                    ) {
                        select(provider: appleVisionProviderId, model: "")
                    }
                }
                // #4883: `roleDefaults` — the shared builder's alias rows,
                // resolved to what each currently names — not the old local
                // `aliasOptions` (deleted; see the type's own doc comment).
                ForEach(roleDefaults) { alias in
                    specialRow(displayName: alias.displayName, isCurrent: selectedProviderId == alias.provider) {
                        select(provider: alias.provider, model: "")
                    }
                }
            }

            if isLoadingProviders {
                Section {
                    ProgressView()
                        .frame(maxWidth: .infinity, alignment: .center)
                }
            } else if availableProviders.isEmpty {
                // No-providers fallback (Default + aliases above stay selectable).
                Section {
                    Text(toolRequiresVision
                         ? "No vision-capable providers available"
                         : "No providers configured")
                        .font(.caption)
                        .foregroundStyle(.orange)
                }
            } else {
                ForEach(availableProviders) { provider in
                    Section(provider.name) {
                        ForEach(provider.models) { model in
                            SharedModelRow(
                                choice: modelChoice(provider: provider, model: model),
                                isCurrent: provider.id == selectedProviderId
                                    && model.id == selectedModelId
                            ) {
                                select(provider: provider.id, model: model.id)
                            }
                            .listRowInsets(EdgeInsets(top: 2, leading: 8, bottom: 2, trailing: 8))
                        }
                    }
                }
            }
        }
        .frame(minWidth: 360, minHeight: 320)
    }

    /// A leading sentinel row (Default / Apple Vision / alias) on the shared row.
    /// Provider+model are blank so the row shows only its label — the trailing
    /// provider text and family mark are for concrete models, not sentinels.
    @ViewBuilder
    private func specialRow(
        displayName: String,
        isCurrent: Bool,
        action: @escaping () -> Void
    ) -> some View {
        SharedModelRow(
            choice: SharedModelChoice(
                provider: "", model: "", displayName: displayName,
                tier: nil, supportsVision: nil, pricing: nil
            ),
            isCurrent: isCurrent,
            action: action
        )
        .listRowInsets(EdgeInsets(top: 2, leading: 8, bottom: 2, trailing: 8))
    }

    private func select(provider: String, model: String) {
        isPresented = false
        if provider == selectedProviderId {
            // Provider unchanged → its `.onChange`/`apply` won't run, so there is
            // no auto-first-model to fight; just move the model binding.
            selectedModelId = model
            return
        }
        // Provider changed → its `.onChange` runs `apply`, which auto-selects the
        // provider's first model. Defer the chosen model to the next main-actor
        // hop so it lands AFTER `apply` and wins — a specific pick must beat the
        // auto-first. Sentinels (empty model) let `apply` set the model itself.
        selectedProviderId = provider
        guard !model.isEmpty else { return }
        let target = model
        Task { @MainActor in selectedModelId = target }
    }

    // MARK: - Derived lists
    //
    // #4883: the old `AliasOption`/`aliasOptions` (a static label, no
    // resolved model) is DELETED — role-default rows now come from the
    // `roleDefaults` param, built once by the caller via the shared
    // `SharedModelListBuilder.roleDefaultAliases`.

    /// Providers offered as concrete rows — the same filter the drill-down used:
    /// enabled only, the catalog Apple row hidden when the tool offers explicit
    /// Apple Vision, and vision-only tools restricted to vision-capable providers.
    private var availableProviders: [ProviderOption] {
        providers.filter { provider in
            guard provider.available else { return false }
            if toolSupportsAppleVision, provider.providerType == "apple" { return false }
            if toolRequiresVision { return provider.supportsVision }
            return true
        }
    }

    /// Re-dress one configured `ModelChoice` as the shared choice the row renders.
    /// The label is the configured name (as the drill-down showed), falling back
    /// to the shortened id only if a row somehow has no name. Vision maps
    /// true→true and false→nil (a provider that never claimed vision is "unknown",
    /// not a definite "no", 2026-09-01); pricing is nil — the configured list
    /// carries no catalog prices, and absent beats invented.
    private func modelChoice(provider: ProviderOption, model: ModelPicker.ModelChoice) -> SharedModelChoice {
        SharedModelChoice(
            provider: provider.id,
            model: model.id,
            displayName: model.name.isEmpty ? ModelChipToolbarItem.shorten(model.id) : model.name,
            tier: nil,
            supportsVision: provider.supportsVision ? true : nil,
            pricing: nil
        )
    }

    /// The concrete provider+model currently selected, if any — drives the chip's
    /// family mark and name. Nil for Default / Apple Vision / alias selections
    /// (those show `currentSpecialLabel` instead).
    private var currentModelChoice: SharedModelChoice? {
        guard !selectedProviderId.isEmpty,
              selectedProviderId != appleVisionProviderId,
              !isModelAliasProviderId(selectedProviderId),
              !selectedModelId.isEmpty,
              let provider = providers.first(where: { $0.id == selectedProviderId })
        else { return nil }
        let label = provider.models.first(where: { $0.id == selectedModelId })?.name
            ?? ModelChipToolbarItem.shorten(selectedModelId)
        return SharedModelChoice(
            provider: provider.id, model: selectedModelId, displayName: label,
            tier: nil, supportsVision: nil, pricing: nil
        )
    }

    /// Chip text for the non-model selections (and a provider chosen before its
    /// model resolves).
    private var currentSpecialLabel: String {
        if selectedProviderId.isEmpty { return "Default" }
        if selectedProviderId == appleVisionProviderId { return "Apple Vision" }
        if isModelAliasProviderId(selectedProviderId) { return selectedProviderId }
        if let provider = providers.first(where: { $0.id == selectedProviderId }) { return provider.name }
        return "Default"
    }

    /// The provider→node mapping, pure so it is unit-testable
    /// (`NodeProviderModelSelectorVisionModeTests`). Returns the model id the
    /// picker should now show ("" hides it).
    ///
    /// `usesLLM` is a TOOL fact (spec `nodeconfig.model.uses-llm-is-tool-fact`):
    /// choosing "Default" must not flip it, because the popover gates the whole
    /// provider section, Compare Models and the Prompt Preview on it — a
    /// Default-provider summarize node used to lose all three on reopen, for good.
    nonisolated static func apply(
        providerId newValue: String,
        to node: inout WorkflowNode,
        providers: [ProviderOption],
        currentModelId: String
    ) -> String {
        // Snapshot the id: `node` is inout, and logger.info's message is an
        // escaping autoclosure — capturing the inout param directly is illegal.
        let nodeId = node.id
        node.config?.removeValue(forKey: "provider_name")
        if newValue.isEmpty {
            // Default selected — clear explicit provider/model so the runtime uses its default
            node.config?.removeValue(forKey: "vision_mode")
            node.providerName = nil
            node.modelName = nil
            return ""
        }

        if newValue == appleVisionProviderId {
            // Apple Vision selected — set vision_mode, clear LLM provider/model.
            // On-device OCR is genuinely not an LLM run, so usesLLM follows.
            if node.config == nil { node.config = [:] }
            node.config?["vision_mode"] = .string("apple")
            node.providerName = nil
            node.modelName = nil
            node.usesLLM = false
            logger.info("Apple Vision selected for node \(nodeId)")
            return ""
        } else if isModelAliasProviderId(newValue) {
            // Tier alias — runtime fills provider+model. Model picker hides.
            node.config?.removeValue(forKey: "vision_mode")
            node.providerName = newValue
            node.modelName = nil
            node.usesLLM = true
            logger.info("Alias \(newValue) selected for node \(nodeId)")
            return ""
        } else {
            // LLM provider selected
            if node.config == nil { node.config = [:] }
            node.config?["vision_mode"] = .string("llm")
            node.providerName = newValue
            node.usesLLM = true
            logger.info("Provider selected: id=\(newValue)")
            if let provider = providers.first(where: { $0.id == newValue }),
               let firstModel = provider.models.first?.id {
                node.modelName = firstModel
                return firstModel
            }
            return currentModelId
        }
    }
}
