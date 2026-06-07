import SwiftUI

struct PresetPickerSheet: View {
    let presets: [ComparisonPreset]
    @Binding var selectedModels: [ModelSpec]
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            List(presets) { preset in
                Button {
                    selectedModels = preset.models.map {
                        ModelSpec(provider: $0.provider, model: $0.model)
                    }
                    dismiss()
                } label: {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(preset.name)
                            .font(.headline)

                        Text(preset.description)
                            .font(.caption)
                            .foregroundStyle(.secondary)

                        Text(preset.models.map(\.model).joined(separator: ", "))
                            .font(.caption2)
                            .foregroundStyle(.tertiary)
                    }
                }
            }
            .navigationTitle("Presets")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
            }
        }
        .frame(minWidth: 400, minHeight: 300)
    }
}
