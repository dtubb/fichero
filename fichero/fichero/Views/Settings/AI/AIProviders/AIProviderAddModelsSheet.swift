import FicheroAPIClient
import OSLog
import SwiftUI

private let logger = Logger(subsystem: "app.fichero.fichero", category: "AIProviderAddModelsSheet")

/// Sheet for adding models to a provider (uses shared AIModelSelectionView)
struct AIProviderAddModelsSheet: View {
    @Environment(\.dismiss) private var dismiss
    let provider: Components.Schemas.ProviderResponse
    let onAdd: () async -> Void

    @State private var selectedModel: ModelInfo?
    @State private var isAdding = false

    // For HuggingFace, show the full browser
    @State private var selectedHFModel: HFModelInfo?

    @Environment(ProviderAPIService.self) var providerService

    var body: some View {
        NavigationStack {
            Group {
                if provider.providerType == "huggingface" {
                    // Use full AIModelCatalog for HuggingFace
                    AIModelCatalog(
                        selectedModel: $selectedHFModel,
                        onModelSelected: { model in
                            selectedHFModel = model
                        }
                    )
                } else {
                    // Use shared AIModelSelectionView with selection mode
                    AIModelSelectionView(
                        providerType: provider.providerType,
                        providerId: provider.id,
                        selectionMode: .select,
                        selectedModel: $selectedModel,
                        onModelAdded: {}
                    )
                }
            }
            .navigationTitle("Add Model to \(provider.name)")
            #if os(iOS)
            .navigationBarTitleDisplayMode(.inline)
            #endif
            // Native sheet actions in the toolbar (correct placement on iOS +
            // macOS) instead of a hand-rolled footer HStack (#2806).
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Add Model") {
                        addModel()
                    }
                    .disabled(isAdding || (selectedModel == nil && selectedHFModel == nil))
                }
            }
        }
        // Mac-only fixed size; iPhone/iPad sheets size to the screen (#2802).
        #if os(macOS)
        .frame(width: 600, height: 600)
        #endif
    }

    private func addModel() {
        isAdding = true

        Task {
            do {
                if let hfModel = selectedHFModel {
                    // HuggingFace model
                    _ = try await providerService.addModel(
                        providerId: provider.id,
                        modelId: hfModel.id,
                        name: hfModel.shortName
                    )
                } else if let model = selectedModel {
                    // Standard model
                    _ = try await providerService.addModel(
                        providerId: provider.id,
                        modelId: model.modelId,
                        name: model.fullName
                    )
                }
                await onAdd()
                dismiss()
            } catch {
                logger.error("Add model failed: \(String(describing: error))")
            }
            isAdding = false
        }
    }
}

/// Card-style row displaying model info with costs and capabilities
struct ModelInfoRow: View {
    let model: ModelInfo
    let isSelected: Bool
    var onSelect: (() -> Void)?  // Optional action when tapped

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            // Header: Name + Recommended badge
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 2) {
                    HStack(spacing: 6) {
                        Text(model.fullName)
                            .font(.headline)

                        if model.isRecommended {
                            Text("Recommended")
                                .font(.caption2)
                                .fontWeight(.medium)
                                .padding(.horizontal, 6)
                                .padding(.vertical, 2)
                                .background(Color.yellow.opacity(0.2))
                                .foregroundColor(.orange)
                                .cornerRadius(4)
                        }
                    }

                    Text(model.modelId)
                        .font(.caption)
                        .foregroundColor(.secondary)
                }

                Spacer()

                // Local badge
                if model.isLocal {
                    HStack(spacing: 4) {
                        Image(systemName: "house.fill")
                            .font(.caption)
                        Text("Local")
                            .font(.caption)
                            .fontWeight(.medium)
                    }
                    .foregroundColor(.green)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(Color.green.opacity(0.1))
                    .cornerRadius(6)
                }
            }

            // Description
            if let description = model.description, !description.isEmpty {
                Text(description)
                    .font(.subheadline)
                    .foregroundColor(.secondary)
                    .lineLimit(2)
            }

            // Capability badges row
            if !model.capabilityBadges.isEmpty {
                HStack(spacing: 6) {
                    ForEach(model.capabilityBadges.prefix(6), id: \.label) { badge in
                        HStack(spacing: 3) {
                            Image(systemName: badge.icon)
                                .font(.caption2)
                            Text(badge.label)
                                .font(.caption2)
                        }
                        .foregroundColor(badge.color)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 3)
                        .background(badge.color.opacity(0.1))
                        .cornerRadius(4)
                    }
                }
            }

            // Pricing and context window row
            HStack(spacing: 16) {
                if model.isLocal {
                    Label("Free", systemImage: "checkmark.circle")
                        .font(.caption)
                        .foregroundColor(.green)
                } else {
                    // Input cost
                    VStack(alignment: .leading, spacing: 1) {
                        Text("Input")
                            .font(.caption2)
                            .foregroundColor(.secondary)
                        Text(model.formattedInputCost)
                            .font(.caption)
                            .fontWeight(.medium)
                    }

                    // Output cost
                    VStack(alignment: .leading, spacing: 1) {
                        Text("Output")
                            .font(.caption2)
                            .foregroundColor(.secondary)
                        Text(model.formattedOutputCost)
                            .font(.caption)
                            .fontWeight(.medium)
                    }
                }

                Spacer()

                // Context window
                if let contextWindow = model.formattedContextWindow {
                    VStack(alignment: .trailing, spacing: 1) {
                        Text("Context")
                            .font(.caption2)
                            .foregroundColor(.secondary)
                        Text(contextWindow)
                            .font(.caption)
                            .fontWeight(.medium)
                    }
                }
            }
        }
        .padding(12)
        .background(isSelected ? Color.accentColor.opacity(0.1) : Color(platformColor: .controlBackgroundColor))
        .cornerRadius(8)
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .stroke(isSelected ? Color.accentColor : Color.clear, lineWidth: 2)
        )
        .contentShape(Rectangle())
        .onTapGesture {
            onSelect?()
        }
    }
}
