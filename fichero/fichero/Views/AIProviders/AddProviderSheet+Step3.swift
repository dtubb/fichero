import FicheroAPIClient
import SwiftUI

// MARK: - Step 3: Model Browser

extension AddProviderSheet {
    var modelLibraryView: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                if let entry = selectedEntry {
                    ProviderLogoView(entry: entry, size: 32)
                }
                Text("Add Models to \(selectedEntry?.name ?? "Provider")")
                    .font(.title2)
                    .fontWeight(.medium)
                Spacer()
            }
            .padding(.horizontal, 20)
            .padding(.top, 16)
            .padding(.bottom, 12)

            Divider()

            // Embed the model browser content with select mode (same as Add Model sheet)
            if let provider = addedProvider {
                AIModelSelectionView(
                    providerType: provider.providerType,
                    providerId: provider.id,
                    selectionMode: .select,
                    selectedModel: $selectedModelForStep3,
                    onModelAdded: {
                        // Clear selection after adding
                        selectedModelForStep3 = nil
                    }
                )
            }

            Divider()

            // Footer with Add Model and Done buttons
            HStack {
                Spacer()

                Button("Add Model") {
                    addModelInStep3()
                }
                .disabled(selectedModelForStep3 == nil || isAddingModel)

                Button("Done") {
                    dismiss()
                }
                .keyboardShortcut(.defaultAction)
            }
            .padding(.horizontal, 20)
            .padding(.vertical, 12)
        }
    }

    func addModelInStep3() {
        guard let model = selectedModelForStep3, let provider = addedProvider else { return }
        isAddingModel = true

        Task { @MainActor in
            do {
                _ = try await providerService.addModel(
                    providerId: provider.id,
                    modelId: model.modelId,
                    name: model.fullName,
                    isDefault: false
                )
                selectedModelForStep3 = nil
                isAddingModel = false
            } catch {
                addProviderLogger.error("Add model failed: \(String(describing: error))")
                isAddingModel = false
            }
        }
    }
}
