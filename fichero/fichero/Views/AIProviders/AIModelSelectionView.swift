import OSLog
import SwiftUI

private let logger = Logger(subsystem: "app.fichero.fichero", category: "AIModelSelectionView")

/// Selection mode for model browser
enum ModelSelectionMode {
    case immediate   // Clicking adds immediately (Add Provider flow)
    case select      // Clicking selects, parent handles adding (Add Model sheet)
}

struct AIModelSelectionView: View {
    let providerType: String
    let providerId: String
    var selectionMode: ModelSelectionMode = .immediate
    @Binding var selectedModel: ModelInfo?
    let onModelAdded: () -> Void

    // Convenience init for immediate mode (no external selection binding needed)
    init(providerType: String, providerId: String, onModelAdded: @escaping () -> Void) {
        self.providerType = providerType
        self.providerId = providerId
        self.selectionMode = .immediate
        self._selectedModel = .constant(nil)
        self.onModelAdded = onModelAdded
    }

    // Full init for select mode
    init(
        providerType: String,
        providerId: String,
        selectionMode: ModelSelectionMode,
        selectedModel: Binding<ModelInfo?>,
        onModelAdded: @escaping () -> Void
    ) {
        self.providerType = providerType
        self.providerId = providerId
        self.selectionMode = selectionMode
        self._selectedModel = selectedModel
        self.onModelAdded = onModelAdded
    }

    @State private var models: [ModelInfo] = []
    @State private var isLoading = true
    @State private var searchText = ""
    @State private var sortOrder: ModelSortOrder = .recommended
    @State private var filters = ModelFilters()

    @Environment(ProviderServiceGenerated.self) var providerService

    private var filteredModels: [ModelInfo] {
        var result = models

        // Apply search filter
        if !searchText.isEmpty {
            result = result.filter {
                $0.modelId.localizedCaseInsensitiveContains(searchText) ||
                    $0.fullName.localizedCaseInsensitiveContains(searchText)
            }
        }

        // Apply capability filters
        if filters.visionOnly { result = result.filter { $0.supportsVision } }
        if filters.reasoningOnly { result = result.filter { $0.supportsReasoning } }
        if filters.toolsOnly { result = result.filter { $0.supportsFunctionCalling } }
        if filters.audioOnly { result = result.filter { $0.supportsAudioInput || $0.supportsAudioOutput } }
        if filters.pdfOnly { result = result.filter { $0.supportsPdfInput } }
        if filters.webSearchOnly { result = result.filter { $0.supportsWebSearch } }
        if filters.batchApiOnly { result = result.filter { $0.supportsBatchApi } }

        // Apply mode filters
        if filters.embeddingsOnly { result = result.filter { $0.mode == "embedding" } }
        if filters.imageGenOnly { result = result.filter { $0.mode == "image_generation" } }
        if filters.speechOnly { result = result.filter { $0.mode == "audio_speech" } }

        // Apply sorting
        switch sortOrder {
        case .recommended:
            result.sort { model1, model2 in
                if model1.isRecommended != model2.isRecommended {
                    return model1.isRecommended
                }
                let comparison = model1.modelId.localizedCaseInsensitiveCompare(model2.modelId)
                return comparison == .orderedAscending
            }
        case .name:
            result.sort { $0.modelId.localizedCaseInsensitiveCompare($1.modelId) == .orderedAscending }
        case .cheapest:
            result.sort {
                let cost0 = $0.inputCostPerMillion + $0.outputCostPerMillion
                let cost1 = $1.inputCostPerMillion + $1.outputCostPerMillion
                return cost0 < cost1
            }
        case .context:
            result.sort { ($0.maxInputTokens ?? 0) > ($1.maxInputTokens ?? 0) }
        }

        return result
    }

    /// Count of active filters
    private var activeFilterCount: Int {
        var count = 0
        if filters.visionOnly { count += 1 }
        if filters.reasoningOnly { count += 1 }
        if filters.toolsOnly { count += 1 }
        if filters.audioOnly { count += 1 }
        if filters.pdfOnly { count += 1 }
        if filters.webSearchOnly { count += 1 }
        if filters.batchApiOnly { count += 1 }
        if filters.embeddingsOnly { count += 1 }
        if filters.imageGenOnly { count += 1 }
        if filters.speechOnly { count += 1 }
        return count
    }

    private var hasActiveFilters: Bool { activeFilterCount > 0 }

    var body: some View {
        VStack(spacing: 0) {
            // Search bar + Sort/Filter controls
            HStack(spacing: 12) {
                // Search
                HStack {
                    Image(systemName: "magnifyingglass")
                        .foregroundColor(.secondary)
                    TextField("Search models...", text: $searchText)
                        .textFieldStyle(.plain)
                }
                .padding(8)
                .background(Color(platformColor: .controlBackgroundColor))
                .cornerRadius(6)

                // Sort picker
                Menu {
                    ForEach(ModelSortOrder.allCases, id: \.self) { order in
                        Button {
                            sortOrder = order
                        } label: {
                            HStack {
                                Text(order.rawValue)
                                if sortOrder == order {
                                    Image(systemName: "checkmark")
                                }
                            }
                        }
                    }
                } label: {
                    HStack(spacing: 4) {
                        Image(systemName: "arrow.up.arrow.down")
                        Text(sortOrder.rawValue)
                            .font(.caption)
                    }
                    .padding(.horizontal, 8)
                    .padding(.vertical, 6)
                    .background(Color(platformColor: .controlBackgroundColor))
                    .cornerRadius(6)
                }
                .menuStyle(.borderlessButton)

                // Filter menu
                Menu {
                    Section("Capabilities") {
                        Toggle("Vision", isOn: $filters.visionOnly)
                        Toggle("Reasoning", isOn: $filters.reasoningOnly)
                        Toggle("Tools/Functions", isOn: $filters.toolsOnly)
                        Toggle("Audio", isOn: $filters.audioOnly)
                        Toggle("PDF Input", isOn: $filters.pdfOnly)
                        Toggle("Web Search", isOn: $filters.webSearchOnly)
                        Toggle("Batch API", isOn: $filters.batchApiOnly)
                    }

                    Section("Mode") {
                        Toggle("Embeddings", isOn: $filters.embeddingsOnly)
                        Toggle("Image Generation", isOn: $filters.imageGenOnly)
                        Toggle("Text to Speech", isOn: $filters.speechOnly)
                    }

                    if hasActiveFilters {
                        Divider()
                        Button("Clear Filters") {
                            filters = ModelFilters()
                        }
                    }
                } label: {
                    HStack(spacing: 4) {
                        let iconName = hasActiveFilters
                            ? "line.3.horizontal.decrease.circle.fill"
                            : "line.3.horizontal.decrease.circle"
                        Image(systemName: iconName)
                        if hasActiveFilters {
                            Text("Filter (\(activeFilterCount))")
                                .font(.caption)
                        } else {
                            Text("Filter")
                                .font(.caption)
                        }
                    }
                    .padding(.horizontal, 8)
                    .padding(.vertical, 6)
                    .background(
                        hasActiveFilters
                            ? Color.accentColor.opacity(0.1)
                            : Color(platformColor: .controlBackgroundColor)
                    )
                    .cornerRadius(6)
                }
                .menuStyle(.borderlessButton)
            }
            .padding()

            // Model list
            if isLoading {
                ProgressView()
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if filteredModels.isEmpty {
                VStack(spacing: 12) {
                    Image(systemName: "cpu")
                        .font(.system(size: 40))
                        .foregroundColor(.secondary)
                    Text("No models found")
                        .foregroundColor(.secondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                List {
                    ForEach(filteredModels) { model in
                        ModelInfoRow(model: model, isSelected: selectedModel?.modelId == model.modelId) {
                            handleModelTap(model)
                        }
                        .listRowInsets(EdgeInsets(top: 4, leading: 16, bottom: 4, trailing: 16))
                        .listRowSeparator(.hidden)
                    }
                }
                .listStyle(.plain)
            }
        }
        .task {
            guard !Task.isCancelled else { return }
            await loadModels()
        }
    }

    private func handleModelTap(_ model: ModelInfo) {
        switch selectionMode {
        case .immediate:
            // Add immediately
            addModel(model)
        case .select:
            // Just select, parent will handle adding
            selectedModel = model
        }
    }

    private func loadModels() async {
        isLoading = true
        defer { isLoading = false }

        do {
            models = try await providerService.listAvailableModels(providerType: providerType)
        } catch {
            logger.error("Load models failed: \(String(describing: error))")
        }
    }

    private func addModel(_ model: ModelInfo) {
        Task {
            do {
                _ = try await providerService.addModel(
                    providerId: providerId,
                    modelId: model.modelId,
                    name: model.fullName,
                    isDefault: false
                )
                onModelAdded()
            } catch {
                logger.error("Add model failed: \(String(describing: error))")
            }
        }
    }
}

/// Apple Mail style radio row - icon + name with radio button
