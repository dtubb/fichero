import FicheroAPIClient
import SwiftUI

// MARK: - Helpers

extension AddProviderSheet {
    /// Whether this provider is added straight from the picker with no configure
    /// step. True for built-in providers AND the app's managed-local runtimes
    /// (MLX/spaCy/Kraken/Whisper), which need no Server URL or API key — their
    /// setup happens inside the provider row. External providers return false and
    /// go to step 2.
    func addsDirectly(_ entry: Components.Schemas.ProviderCatalogResponse?) -> Bool {
        guard let entry else { return false }
        return entry.isBuiltin || ManagedLocalRuntime.contains(entry.providerType)
    }

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

                // Managed-local runtimes have no reference-model browser (their
                // installable models live in the provider row's On-Device
                // section) — dismiss instead of landing on an empty step-3.
                // External providers go to the model browser as before.
                if ManagedLocalRuntime.contains(type) {
                    dismiss()
                } else {
                    addedProvider = result
                    step = 3
                }
            } catch {
                addProviderLogger.error("Add failed: \(String(describing: error))")
                isAdding = false
            }
        }
    }
}
