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
                // A rejected add must never read as "added" — Ann added
                // Gemini, closed the window, and the model was gone with no
                // message (2026-08-24). The error is user-facing, not a log.
                if let addModelError {
                    Text(addModelError)
                        .font(.callout)
                        .foregroundStyle(.red)
                        .lineLimit(2)
                }
                Spacer()

                Button("Add Model") {
                    addModelInStep3()
                }
                .disabled(selectedModelForStep3 == nil || isAddingModel)

                // Done ADDS the staged selection first (Ann, 2026-08-24: she
                // clicked the Gemini row — which highlights exactly like
                // "added" — then pressed the default button, and the model
                // evaporated). A visible selection is intent; Done honors it,
                // and stays open if that add fails so the error is seen.
                Button("Done") {
                    if selectedModelForStep3 != nil {
                        addModelInStep3(thenDismiss: true)
                    } else {
                        dismiss()
                    }
                }
                .keyboardShortcut(.defaultAction)
                .disabled(isAddingModel)
            }
            .padding(.horizontal, 20)
            .padding(.vertical, 12)
        }
    }

    func addModelInStep3(thenDismiss: Bool = false) {
        guard let model = selectedModelForStep3, let provider = addedProvider else { return }
        isAddingModel = true
        addModelError = nil

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
                if thenDismiss { dismiss() }
            } catch {
                addProviderLogger.error("Add model failed: \(String(describing: error))")
                addModelError = "Couldn't add \(model.modelId): \(error.localizedDescription)"
                isAddingModel = false
            }
        }
    }
}
