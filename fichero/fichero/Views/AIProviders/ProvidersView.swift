import FicheroAPIClient
import OSLog
import SwiftUI

let providersViewLogger = Logger(subsystem: "com.fichero.fichero", category: "ProvidersView")

struct ProvidersView: View {
    @EnvironmentObject var appState: AppState
    @State private var providers: [Components.Schemas.ProviderResponse] = []
    @State private var catalog: [Components.Schemas.ProviderCatalogResponse] = []
    @State private var isLoading = true
    @State private var showAddProvider = false
    @State private var selectedProvider: Components.Schemas.ProviderResponse?

    @EnvironmentObject var providerService: ProviderServiceGenerated

    var body: some View {
        HSplitView {
            VStack(alignment: .leading, spacing: 0) {
                List(selection: $selectedProvider) {
                    ForEach(sortedProviders) { provider in
                        ProviderSettingsRow(
                            provider: provider,
                            catalogEntry: catalog.first { $0.providerType == provider.providerType }
                        )
                        .tag(provider)
                    }
                }
                .listStyle(.sidebar)

                Divider()

                HStack(spacing: 4) {
                    Button {
                        showAddProvider = true
                    } label: {
                        Image(systemName: "plus")
                    }
                    .buttonStyle(.borderless)

                    Button(action: deleteSelectedProvider) {
                        Image(systemName: "minus")
                    }
                    .buttonStyle(.borderless)
                    .disabled(selectedProvider == nil)

                    Spacer()
                }
                .padding(8)
            }
            .frame(minWidth: 200, maxWidth: 250)

            if let provider = selectedProvider {
                ProviderDetailView(
                    provider: provider,
                    catalogEntry: catalog.first { $0.providerType == provider.providerType },
                    onUpdate: loadProviders
                )
                .frame(minWidth: 350)
            } else {
                VStack {
                    Image(systemName: "cpu")
                        .font(.system(size: 48))
                        .foregroundColor(.secondary)
                    Text("Select a provider")
                        .foregroundColor(.secondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .task {
            guard !Task.isCancelled else { return }
            await loadProviders()
        }
        .sheet(isPresented: $showAddProvider) {
            AddProviderSheet(onAdd: loadProviders, isFirstLaunch: false)
        }
    }

    var sortedProviders: [Components.Schemas.ProviderResponse] {
        providers
            .sorted { provider1, provider2 in
                let orderA = sortOrder(provider1.providerType)
                let orderB = sortOrder(provider2.providerType)
                if orderA < 100 && orderB < 100 {
                    return orderA < orderB
                }
                if orderA < 100 { return true }
                if orderB < 100 { return false }
                return provider1.name.localizedCaseInsensitiveCompare(provider2.name) == .orderedAscending
            }
    }

    func sortOrder(_ type: String) -> Int {
        switch type {
        case "apple", "apple_vision", "apple_intelligence": return 0
        case "openai": return 1
        default: return 100
        }
    }

    func loadProviders() async {
        isLoading = true
        defer { isLoading = false }

        do {
            providers = try await providerService.listProviders()
            catalog = try await providerService.listCatalog()
        } catch {
            providersViewLogger.error("Failed to load: \(String(describing: error))")
        }
    }

    func deleteSelectedProvider() {
        guard let provider = selectedProvider else { return }
        Task {
            do {
                try await providerService.deleteProvider(provider.id)
                selectedProvider = nil
                await loadProviders()
            } catch {
                providersViewLogger.error("Delete failed: \(String(describing: error))")
            }
        }
    }
}

// MARK: - Preview

#Preview {
    let appState = AppState()

    ProvidersView()
        .environmentObject(appState)
        .environmentObject(appState.providerService)
        .environmentObject(appState.modelService)
        .frame(width: 900, height: 600)
}
