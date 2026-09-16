import SwiftUI

struct ModelPickerSheet: View {
    let availableModels: [ComparisonModelInfo]
    @Binding var selectedModels: [ModelSpec]
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            List(availableModels) { model in
                // The SHARED row every picker draws (spec RATIFIED 2026-09-15) —
                // family mark, shortened name over per-million price, the same
                // face the island and workflow bar show. The comparison
                // catalog is its own list source (the service, not the provider
                // cache), so only the ROW converges here; the choice is a
                // straight re-dress of one `ComparisonModelInfo`.
                SharedModelRow(
                    choice: sharedChoice(for: model),
                    isCurrent: isSelected(model)
                ) {
                    if !isSelected(model) {
                        selectedModels.append(
                            ModelSpec(provider: model.provider, model: model.model))
                    }
                    dismiss()
                }
                .listRowInsets(EdgeInsets(top: 2, leading: 8, bottom: 2, trailing: 8))
            }
            .navigationTitle("Add Model")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
            }
        }
        .frame(minWidth: 400, minHeight: 400)
    }

    private func isSelected(_ model: ComparisonModelInfo) -> Bool {
        selectedModels.contains { $0.provider == model.provider && $0.model == model.model }
    }

    /// Re-dress one comparison-catalog entry as the shared choice the row
    /// renders. Vision is `nil` — the comparison catalog reports no vision
    /// flag, and absent is not a "no" (2026-09-01). Pricing comes straight
    /// from the catalog's per-million figures.
    private func sharedChoice(for model: ComparisonModelInfo) -> SharedModelChoice {
        SharedModelChoice(
            provider: model.provider,
            model: model.model,
            displayName: ModelChipToolbarItem.shorten(model.model),
            tier: nil,
            supportsVision: nil,
            pricing: SharedModelPricing(
                inputPerMillion: model.inputPricePerMillion,
                outputPerMillion: model.outputPricePerMillion
            )
        )
    }
}
