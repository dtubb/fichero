import FicheroAPIClient
import SwiftUI

// MARK: - Helpers

extension AddProviderSheet {
    func defaultServerUrl(for type: String) -> String {
        switch type {
        case "ollama": return "http://localhost:11434"
        case "lmstudio": return "http://localhost:1234"
        case "omlx": return "http://localhost:8000/v1"
        default: return ""
        }
    }

    func loadCatalog() async {
        isLoading = true
        defer { isLoading = false }

        do {
            // Load catalog and existing providers
            catalog = try await providerService.listCatalog()
            let existingProviders = try await providerService.listProviders()
            existingProviderTypes = Set(existingProviders.map { $0.providerType })

            if let selectedType, !availableCatalog.contains(where: { $0.providerType == selectedType }) {
                self.selectedType = nil
            }

            // Pre-select first available local provider for first launch
            if isFirstLaunch, let first = availableCatalog.first(where: { $0.isLocal }) {
                selectedType = first.providerType
            } else if selectedType == nil, let first = availableCatalog.first {
                // Pre-select first available if nothing selected
                selectedType = first.providerType
            }
        } catch {
            addProviderLogger.error("Load catalog failed: \(String(describing: error))")
        }
    }

    func addProvider() {
        addProviderLogger.info("addProvider() called, selectedType=\(selectedType ?? "nil")")
        guard let type = selectedType else {
            addProviderLogger.warning("selectedType is nil, returning early")
            return
        }
        isAdding = true

        Task { @MainActor in
            do {
                let apiBase = serverUrl.isEmpty ? nil : serverUrl
                addProviderLogger.info("Creating provider type=\(type), apiBase=\(apiBase ?? "nil")")

                let result = try await providerService.createProvider(
                    providerType: type,
                    apiBase: apiBase,
                    apiKey: apiKey.isEmpty ? nil : apiKey
                )
                addProviderLogger.info("Provider created: \(result.id)")
                await onAdd()
                isAdding = false

                // Store the added provider and go to model browser
                addedProvider = result
                step = 3
            } catch {
                addProviderLogger.error("Add failed: \(String(describing: error))")
                isAdding = false
            }
        }
    }
}
