import FicheroAPIClient
import OSLog
import SwiftUI

private let pickerLogger = Logger(subsystem: "app.fichero.fichero", category: "SettingsModelPicker")

/// One Defaults slot's model chooser, on the SHARED picker row so a model in
/// Settings looks identical to the same model in the document island and the
/// workflow bar (spec RATIFIED 2026-09-15,
/// docs/contributor_manual/specs/ui/model-selector-consistency.md).
///
/// This replaces the old Provider→Model two-dropdown DRILL-DOWN (`ModelPicker`,
/// "Spine B") the creative director's ruling forbids: choosing a model is now
/// ONE step. A single chip opens a popover that lists every configured model,
/// grouped by provider, each rendered by `SharedModelRow` — the same row every
/// other picker surface draws. Picking a row writes BOTH bindings at once
/// (provider = its providerType, model = its id), so the caller's `.onChange`
/// provider handlers in `AISettingsView+Tabs` keep firing exactly as before.
///
/// Source parity, not builder parity (the `ModelPickerSheet` precedent): the
/// shared `SharedModelListBuilder` takes `[LLMProvider]`, but Settings' source
/// is `[ModelInfo]` carrying the per-model capability strings the tier filter
/// (`TierCapability.matches`) needs and the configured `fullName` labels this
/// surface shows. So only the ROW converges here; each `ModelInfo` is
/// re-dressed as the same `SharedModelChoice` the builder would emit.
struct SettingsSharedModelPicker: View {
    let appState: AppState
    /// The Defaults slot's provider — keyed by providerType (matches the store).
    @Binding var providerSelection: String
    /// The Defaults slot's model id.
    @Binding var modelSelection: String
    /// Capability requirement for this tier; only matching models are offered.
    let tier: AISettingsView.TierCapability
    /// The list the caller already loaded for the selected provider — used as a
    /// seed so the current provider's models show before the full fetch lands.
    let seedModels: [ModelInfo]

    /// Every configured provider's models, keyed by providerType. Loaded once on
    /// appear (Settings is low-frequency; reopening refreshes, matching the
    /// existing "reopen Defaults to see a just-added model" behaviour).
    @State private var modelsByType: [String: [ModelInfo]] = [:]
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
        .task {
            // Seed the selected provider so its models are visible immediately.
            if !providerSelection.isEmpty, modelsByType[providerSelection] == nil {
                modelsByType[providerSelection] = seedModels
            }
            await loadAll()
        }
        .help("Every configured model is listed; a model not marked for this "
              + "slot's capability is shown greyed, with the reason as its "
              + "tooltip — never hidden.")
    }

    // MARK: - Chip

    @ViewBuilder
    private var chipLabel: some View {
        HStack(spacing: 6) {
            if let current = currentChoice {
                ModelFamilyMark(model: current.model, provider: current.provider)
                Text(current.displayName)
                    .lineLimit(1)
            } else {
                Text("None")
                    .foregroundStyle(.secondary)
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
            Section {
                SharedModelRow(
                    choice: SharedModelChoice(
                        provider: "", model: "", displayName: "None",
                        tier: nil, supportsVision: nil, pricing: nil
                    ),
                    isCurrent: providerSelection.isEmpty || modelSelection.isEmpty
                ) {
                    select(provider: "", model: "")
                }
                .listRowInsets(EdgeInsets(top: 2, leading: 8, bottom: 2, trailing: 8))
            }

            ForEach(providerGroups, id: \.providerType) { group in
                Section(group.name) {
                    ForEach(group.rows, id: \.choice.id) { row in
                        SharedModelRow(
                            choice: row.choice,
                            isCurrent: row.choice.provider == providerSelection
                                && row.choice.model == modelSelection,
                            disabledReason: row.disabledReason
                        ) {
                            select(provider: row.choice.provider, model: row.choice.model)
                        }
                        .listRowInsets(EdgeInsets(top: 2, leading: 8, bottom: 2, trailing: 8))
                    }
                }
            }
        }
        .frame(minWidth: 360, minHeight: 320)
    }

    private func select(provider: String, model: String) {
        // Provider first, then model: the caller's provider `.onChange` resets
        // the model to "" and async-reloads, but its race guard (#1344) restores
        // a selection already valid in the new list — which this one is.
        providerSelection = provider
        modelSelection = model
        isPresented = false
    }

    // MARK: - Derived lists

    /// One provider and its rows — EVERY configured model, never filtered out
    /// (mark-never-remove, spec RATIFIED 2026-09-15): a row whose capabilities
    /// don't fit this slot's tier is still listed, just greyed with a reason
    /// (`disabledReason`), the same way the island greys a non-vision model
    /// for a vision selection. Dropping the row entirely — the old
    /// behaviour — made a vision-capable frontier model saved with only
    /// `["vision"]` unpickable for $medium/$large ("why isn't Opus here").
    private struct ProviderGroup {
        let providerType: String
        let name: String
        let rows: [(choice: SharedModelChoice, disabledReason: String?)]
    }

    private var providerGroups: [ProviderGroup] {
        // De-duplicate providers by providerType (the store's key) so a backend
        // returning two rows of one type does not double a section.
        let uniqueProviders = Array(
            Dictionary(grouping: appState.providers, by: { $0.providerType })
                .compactMapValues { $0.first }
                .values
        ).sorted(by: { $0.name < $1.name })

        return uniqueProviders.compactMap { provider in
            let infos = modelsByType[provider.providerType] ?? []
            guard !infos.isEmpty else { return nil }
            return ProviderGroup(
                providerType: provider.providerType,
                name: provider.name,
                rows: infos.map { info in
                    let reason = tier.matches(info) ? nil :
                        "Not marked for \(tier.displayName) — edit its capabilities "
                        + "in Models & Providers"
                    return (Self.choice(from: info), reason)
                }
            )
        }
    }

    /// The row for the current selection, if it is in a loaded list.
    private var currentChoice: SharedModelChoice? {
        guard !providerSelection.isEmpty, !modelSelection.isEmpty else { return nil }
        if let info = modelsByType[providerSelection]?
            .first(where: { $0.modelId == modelSelection }) {
            return Self.choice(from: info)
        }
        // Selected but not (yet) loaded: still show the id so the chip is never
        // blank on a valid selection.
        return SharedModelChoice(
            provider: providerSelection,
            model: modelSelection,
            displayName: ModelChipToolbarItem.shorten(modelSelection),
            tier: nil, supportsVision: nil, pricing: nil
        )
    }

    /// Re-dress one `ModelInfo` as the shared choice the row renders. The
    /// configured `fullName` is the label (as Settings always showed);
    /// `supportsVision` maps true→true and false→nil, because a configured row
    /// that never claimed vision is "unknown", not a definite "no" (2026-09-01).
    /// Pricing is nil — the configured list carries no catalog prices, and
    /// absent beats invented.
    private static func choice(from info: ModelInfo) -> SharedModelChoice {
        SharedModelChoice(
            provider: info.provider ?? "",
            model: info.modelId,
            displayName: info.fullName.isEmpty
                ? ModelChipToolbarItem.shorten(info.modelId)
                : info.fullName,
            tier: nil,
            supportsVision: info.supportsVision ? true : nil,
            pricing: nil
        )
    }

    // MARK: - Loading

    /// Load every configured provider's model list once, so the popover offers
    /// them all in one step. Shows ONLY user-configured models (the same source
    /// the drill-down used) — never the catalog, whose names can 404 at runtime.
    @MainActor
    private func loadAll() async {
        for provider in appState.providers {
            do {
                let configured = try await appState.providerService
                    .listProviderModels(providerId: provider.id)
                modelsByType[provider.providerType] = AISettingsView
                    .configuredModelInfos(from: configured, providerType: provider.providerType)
            } catch {
                pickerLogger.error(
                    "Failed to load models for \(provider.providerType): \(error.localizedDescription)"
                )
            }
        }
    }
}

// MARK: - Previews

// The chip as Settings' Defaults rows show it. `seedModels: []` is deliberate: the
// picker must render its label from the CURRENT selection before any catalog loads —
// an empty seed is the state a user actually sees on first open, so it is the state
// worth pinning.
#Preview("Defaults chip — vision tier") {
    SettingsSharedModelPicker(
        appState: AppState(),
        providerSelection: .constant("anthropic"),
        modelSelection: .constant("claude-sonnet-5"),
        tier: .vision,
        seedModels: []
    )
    .padding()
}

#Preview("Defaults chip — nothing chosen yet") {
    SettingsSharedModelPicker(
        appState: AppState(),
        providerSelection: .constant(""),
        modelSelection: .constant(""),
        tier: .text,
        seedModels: []
    )
    .padding()
}
