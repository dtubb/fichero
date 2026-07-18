import FicheroAPIClient
import OSLog
import SwiftUI

let addProviderLogger = Logger(subsystem: "app.fichero.fichero", category: "AddProviderSheet")

struct AddProviderSheet: View {
    @Environment(\.dismiss) var dismiss
    let onAdd: () async -> Void
    let isFirstLaunch: Bool

    @State var catalog: [Components.Schemas.ProviderCatalogResponse] = []
    @State var existingProviderTypes: Set<String> = []  // Already configured
    @State var selectedType: String?
    @State var apiKey: String = ""
    @State var serverUrl: String = ""
    @State var isLoading = true
    @State var isAdding = false
    @State var step: Int = 1  // 1 = choose, 2 = configure, 3 = models
    @State var addedProvider: Components.Schemas.ProviderResponse?  // The provider we just added
    @State var selectedModelForStep3: ModelInfo?  // Selected model in step 3
    @State var isAddingModel = false

    @Environment(ProviderAPIService.self) var providerService

    init(onAdd: @escaping () async -> Void, isFirstLaunch: Bool = false) {
        self.onAdd = onAdd
        self.isFirstLaunch = isFirstLaunch
    }

    /// Currently selected catalog entry
    var selectedEntry: Components.Schemas.ProviderCatalogResponse? {
        catalog.first { $0.providerType == selectedType }
    }

    /// Catalog entries that haven't been added yet
    var availableCatalog: [Components.Schemas.ProviderCatalogResponse] {
        catalog.filter {
            !existingProviderTypes.contains($0.providerType)
        }
    }

    var body: some View {
        VStack(spacing: 0) {
            if step == 1 {
                // Step 1: Choose provider (Apple Mail style)
                chooseProviderView
            } else if step == 2 {
                // Step 2: Configure (API key or server URL)
                configureProviderView
            } else {
                // Step 3: Browse/add models for the new provider
                modelLibraryView
            }
        }
        .frame(width: step == 3 ? 600 : 420, height: step == 1 ? 480 : (step == 2 ? 340 : 500))
        .task {
            guard !Task.isCancelled else { return }
            await loadCatalog()
        }
    }
}

struct ProviderRadioRow: View {
    let entry: Components.Schemas.ProviderCatalogResponse
    let isSelected: Bool
    let onSelect: () -> Void

    var body: some View {
        Button(action: onSelect) {
            HStack(spacing: 16) {
                // Radio button
                Image(systemName: isSelected ? "circle.inset.filled" : "circle")
                    .font(.title2)
                    .foregroundColor(isSelected ? .accentColor : .secondary)

                // Provider logo (bundled image or SF Symbol fallback)
                ProviderLogoView(entry: entry, size: 28)

                Text(entry.name)
                    .font(.title3)
                    .foregroundColor(.primary)

                Spacer()

                // Show checkmark if already configured
                if entry.hasApiKey {
                    Image(systemName: "checkmark.circle.fill")
                        .foregroundColor(.green)
                        .font(.body)
                }
            }
            .padding(.vertical, 8)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }
}
