import SwiftUI

extension ModelComparisonView {
    var sidebar: some View {
        VStack(spacing: 0) {
            promptSection
            Divider()
            modelSection
            Divider()
            actionSection
            Divider()
            historySection
        }
        .navigationTitle("Compare Models")
    }

    var promptSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Prompt")
                .font(.headline)

            MacPlainTextEditor(text: $prompt, font: .preferredFont(forTextStyle: .body))
                .frame(minHeight: 100)
                .overlay(
                    RoundedRectangle(cornerRadius: 6)
                        .stroke(Color.secondary.opacity(0.3), lineWidth: 1)
                )

            DisclosureGroup("System Prompt (Optional)") {
                TextField("System instructions...", text: $systemPrompt, axis: .vertical)
                    .lineLimit(3...6)
                    .textFieldStyle(.roundedBorder)
            }
            .font(.subheadline)
        }
        .padding()
    }

    var modelSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("Models (\(selectedModels.count))")
                    .font(.headline)

                Spacer()

                Button {
                    showingPresets = true
                } label: {
                    Image(systemName: "list.bullet.rectangle")
                }
                .buttonStyle(.borderless)
                .help("Load preset")

                Button {
                    showingModelPicker = true
                } label: {
                    Image(systemName: "plus")
                }
                .buttonStyle(.borderless)
                .help("Add model")
            }

            if selectedModels.isEmpty {
                Text("No models selected")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } else {
                ForEach(selectedModels) { model in
                    HStack {
                        VStack(alignment: .leading) {
                            Text(model.model)
                                .font(.subheadline)
                            Text(model.provider)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }

                        Spacer()

                        Button {
                            selectedModels.removeAll { $0.id == model.id }
                        } label: {
                            Image(systemName: "xmark.circle.fill")
                                .foregroundStyle(.secondary)
                        }
                        .buttonStyle(.borderless)
                    }
                    .padding(8)
                    .background(.quaternary.opacity(0.5))
                    .cornerRadius(6)
                }
            }
        }
        .padding()
        .sheet(isPresented: $showingModelPicker) {
            ModelPickerSheet(
                availableModels: service.availableModels,
                selectedModels: $selectedModels
            )
        }
        .sheet(isPresented: $showingPresets) {
            PresetPickerSheet(
                presets: service.presets,
                selectedModels: $selectedModels
            )
        }
    }

    var actionSection: some View {
        VStack(spacing: 12) {
            Button {
                Task {
                    await service.compare(
                        prompt: prompt,
                        models: selectedModels,
                        systemPrompt: systemPrompt.isEmpty ? nil : systemPrompt
                    )
                }
            } label: {
                if service.isComparing {
                    ProgressView()
                        .controlSize(.small)
                } else {
                    Label("Compare Models", systemImage: "play.fill")
                }
            }
            .buttonStyle(.borderedProminent)
            .disabled(prompt.isEmpty || selectedModels.isEmpty || service.isComparing)

            if let error = service.error {
                Text(error)
                    .font(.caption)
                    .foregroundStyle(.red)
            }
        }
        .padding()
    }

    var historySection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("History")
                .font(.headline)

            if service.history.isEmpty {
                Text("No previous comparisons")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } else {
                List(selection: historySelection) {
                    ForEach(service.history) { result in
                        historyRow(result)
                            .tag(result.id)
                    }
                }
                .listStyle(.inset)
            }
        }
        .padding()
    }

    /// Selection binding bridging the native List to the service's current result.
    private var historySelection: Binding<ComparisonResult.ID?> {
        Binding(
            get: { service.lastResult?.id },
            set: { newID in
                if let newID, let match = service.history.first(where: { $0.id == newID }) {
                    service.lastResult = match
                }
            }
        )
    }

    @ViewBuilder
    private func historyRow(_ result: ComparisonResult) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(result.prompt.prefix(50) + (result.prompt.count > 50 ? "..." : ""))
                .font(.caption)
                .lineLimit(2)
                .multilineTextAlignment(.leading)

            HStack {
                Text("\(result.modelsCompared.count) models")
                    .font(.caption2)
                    .foregroundStyle(.secondary)

                Spacer()

                Text(String(format: "$%.4f", result.totalCostUsd))
                    .font(.caption2)
                    .foregroundStyle(.green)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.vertical, 2)
    }
}
