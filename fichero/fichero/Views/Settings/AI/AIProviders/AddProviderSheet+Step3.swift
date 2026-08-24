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

            // Click-to-add (Daniel, 2026-08-24: "we don't need to click
            // Done"). The staged select-then-confirm flow is what lost Ann's
            // Gemini model — a highlighted row read as "added" and the
            // default-action Done discarded it. Immediate mode adds on the
            // row click, the row grows a green check, and a failed add shows
            // in red inside the browser.
            if let provider = addedProvider {
                AIModelSelectionView(
                    providerType: provider.providerType,
                    providerId: provider.id,
                    selectionMode: .immediate,
                    selectedModel: $selectedModelForStep3,
                    onModelAdded: {}
                )
            }

            Divider()

            HStack {
                Spacer()
                Button("Done") { dismiss() }
                    .keyboardShortcut(.defaultAction)
            }
            .padding(.horizontal, 20)
            .padding(.vertical, 12)
        }
    }
}
