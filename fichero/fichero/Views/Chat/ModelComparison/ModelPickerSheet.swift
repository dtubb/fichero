import SwiftUI

struct ModelPickerSheet: View {
    let availableModels: [ComparisonModelInfo]
    @Binding var selectedModels: [ModelSpec]
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            List(availableModels) { model in
                Button {
                    if !selectedModels.contains(where: { $0.provider == model.provider && $0.model == model.model }) {
                        selectedModels.append(ModelSpec(provider: model.provider, model: model.model))
                    }
                    dismiss()
                } label: {
                    HStack {
                        VStack(alignment: .leading) {
                            Text(model.model)
                                .font(.headline)
                            Text(model.provider)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }

                        Spacer()

                        VStack(alignment: .trailing) {
                            Text("In: $\(String(format: "%.2f", model.inputPricePerMillion))/M")
                                .font(.caption2)
                            Text("Out: $\(String(format: "%.2f", model.outputPricePerMillion))/M")
                                .font(.caption2)
                        }
                        .foregroundStyle(.secondary)
                    }
                }
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
}
