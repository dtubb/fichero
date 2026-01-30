import SwiftUI
import OSLog

/// View for comparing responses across multiple LLM models
struct ModelComparisonView: View {
    @StateObject private var service = ModelComparisonService()
    @State private var prompt = ""
    @State private var systemPrompt = ""
    @State private var selectedModels: [ModelSpec] = [
        ModelSpec(provider: "openai", model: "gpt-4o"),
        ModelSpec(provider: "anthropic", model: "claude-3-5-sonnet-20241022"),
    ]
    @State private var showingModelPicker = false
    @State private var showingPresets = false

    var body: some View {
        NavigationSplitView {
            sidebar
                .navigationSplitViewColumnWidth(min: 250, ideal: 300)
        } detail: {
            if let result = service.lastResult {
                ComparisonResultView(result: result)
            } else {
                ContentUnavailableView(
                    "No Comparison",
                    systemImage: "square.split.2x2",
                    description: Text("Enter a prompt and select models to compare")
                )
            }
        }
        .task {
            await service.loadModels()
            await service.loadPresets()
        }
    }

    // MARK: - Sidebar

    private var sidebar: some View {
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

    private var promptSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Prompt")
                .font(.headline)

            TextEditor(text: $prompt)
                .font(.body)
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

    private var modelSection: some View {
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

    private var actionSection: some View {
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

    private var historySection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("History")
                .font(.headline)

            if service.history.isEmpty {
                Text("No previous comparisons")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } else {
                ScrollView {
                    LazyVStack(spacing: 8) {
                        ForEach(service.history.prefix(5)) { result in
                            Button {
                                service.lastResult = result
                            } label: {
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
                                .padding(8)
                                .background(.quaternary.opacity(0.5))
                                .cornerRadius(6)
                            }
                            .buttonStyle(.plain)
                        }
                    }
                }
            }
        }
        .padding()
    }
}

// MARK: - Comparison Result View

struct ComparisonResultView: View {
    let result: ComparisonResult

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                // Summary header
                summaryHeader

                Divider()

                // Model results in grid
                LazyVGrid(columns: gridColumns, spacing: 16) {
                    ForEach(result.results) { modelResult in
                        ModelResultCard(
                            result: modelResult,
                            isFastest: result.fastestModel == modelResult.id,
                            isCheapest: result.cheapestModel == modelResult.id
                        )
                    }
                }
            }
            .padding()
        }
        .navigationTitle("Comparison Results")
    }

    private var gridColumns: [GridItem] {
        [GridItem(.adaptive(minimum: 400, maximum: 600), spacing: 16)]
    }

    private var summaryHeader: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Prompt")
                .font(.headline)

            Text(result.prompt)
                .font(.body)
                .padding()
                .background(.quaternary.opacity(0.3))
                .cornerRadius(8)

            HStack(spacing: 24) {
                StatBadge(
                    label: "Models",
                    value: "\(result.modelsCompared.count)",
                    icon: "cpu"
                )

                StatBadge(
                    label: "Total Cost",
                    value: String(format: "$%.4f", result.totalCostUsd),
                    icon: "dollarsign.circle"
                )

                StatBadge(
                    label: "Total Time",
                    value: String(format: "%.0fms", result.totalLatencyMs),
                    icon: "clock"
                )

                if let fastest = result.fastestModel {
                    StatBadge(
                        label: "Fastest",
                        value: fastest.split(separator: "/").last.map(String.init) ?? fastest,
                        icon: "bolt.fill"
                    )
                }
            }
        }
    }
}

struct StatBadge: View {
    let label: String
    let value: String
    let icon: String

    var body: some View {
        HStack(spacing: 6) {
            Image(systemName: icon)
                .foregroundStyle(.secondary)

            VStack(alignment: .leading, spacing: 2) {
                Text(label)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                Text(value)
                    .font(.subheadline)
                    .fontWeight(.medium)
            }
        }
        .padding(8)
        .background(.quaternary.opacity(0.5))
        .cornerRadius(6)
    }
}

// MARK: - Model Result Card

struct ModelResultCard: View {
    let result: ModelResult
    let isFastest: Bool
    let isCheapest: Bool

    @State private var isExpanded = true

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            // Header
            HStack {
                VStack(alignment: .leading) {
                    HStack {
                        Text(result.model)
                            .font(.headline)

                        if isFastest {
                            Image(systemName: "bolt.fill")
                                .foregroundStyle(.yellow)
                                .help("Fastest response")
                        }

                        if isCheapest {
                            Image(systemName: "dollarsign.circle.fill")
                                .foregroundStyle(.green)
                                .help("Lowest cost")
                        }
                    }

                    Text(result.provider)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                Spacer()

                VStack(alignment: .trailing) {
                    Text(String(format: "%.0fms", result.latencyMs))
                        .font(.caption)
                        .foregroundStyle(.secondary)

                    Text(String(format: "$%.4f", result.costUsd))
                        .font(.caption)
                        .foregroundStyle(.green)
                }
            }

            // Response
            if let error = result.error {
                Text(error)
                    .font(.body)
                    .foregroundStyle(.red)
                    .padding()
                    .background(.red.opacity(0.1))
                    .cornerRadius(6)
            } else {
                Text(result.response)
                    .font(.body)
                    .padding()
                    .background(.quaternary.opacity(0.3))
                    .cornerRadius(6)
                    .lineLimit(isExpanded ? nil : 5)
                    .onTapGesture {
                        withAnimation {
                            isExpanded.toggle()
                        }
                    }
            }

            // Token stats
            HStack {
                Label("\(result.inputTokens) in", systemImage: "arrow.down.circle")
                Label("\(result.outputTokens) out", systemImage: "arrow.up.circle")
            }
            .font(.caption2)
            .foregroundStyle(.secondary)
        }
        .padding()
        .background(.background)
        .cornerRadius(12)
        .shadow(color: .black.opacity(0.1), radius: 4, y: 2)
    }
}

// MARK: - Model Picker Sheet

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

// MARK: - Preset Picker Sheet

struct PresetPickerSheet: View {
    let presets: [ComparisonPreset]
    @Binding var selectedModels: [ModelSpec]
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            List(presets) { preset in
                Button {
                    selectedModels = preset.models.compactMap { dict in
                        guard let provider = dict["provider"], let model = dict["model"] else { return nil }
                        return ModelSpec(provider: provider, model: model)
                    }
                    dismiss()
                } label: {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(preset.name)
                            .font(.headline)

                        Text(preset.description)
                            .font(.caption)
                            .foregroundStyle(.secondary)

                        Text(preset.models.compactMap { $0["model"] }.joined(separator: ", "))
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

#Preview {
    ModelComparisonView()
}
