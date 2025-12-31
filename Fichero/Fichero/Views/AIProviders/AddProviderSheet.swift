import SwiftUI
import OSLog

private let logger = Logger(subsystem: "ca.tubb.Fichero", category: "AddProviderSheet")

struct AddProviderSheet: View {
    @Environment(\.dismiss) private var dismiss
    let onAdd: () async -> Void
    let isFirstLaunch: Bool

    @State private var catalog: [ProviderCatalogEntry] = []
    @State private var existingProviderTypes: Set<String> = []  // Already configured
    @State private var selectedType: String?
    @State private var apiKey: String = ""
    @State private var serverUrl: String = ""
    @State private var isLoading = true
    @State private var isAdding = false
    @State private var step: Int = 1  // 1 = choose, 2 = configure, 3 = models
    @State private var addedProvider: ProviderResponse?  // The provider we just added
    @State private var selectedModelForStep3: ModelInfo?  // Selected model in step 3
    @State private var isAddingModel = false

    private let providerService = ProviderService(apiClient: APIClient())

    init(onAdd: @escaping () async -> Void, isFirstLaunch: Bool = false) {
        self.onAdd = onAdd
        self.isFirstLaunch = isFirstLaunch
    }

    /// Currently selected catalog entry
    private var selectedEntry: ProviderCatalogEntry? {
        catalog.first { $0.type == selectedType }
    }

    /// Catalog entries that haven't been added yet
    private var availableCatalog: [ProviderCatalogEntry] {
        catalog.filter { !existingProviderTypes.contains($0.type) }
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
        .frame(width: step == 3 ? 600 : 420, height: step == 1 ? 480 : (step == 2 ? 280 : 500))
        .task {
            await loadCatalog()
        }
    }

    // MARK: - Step 1: Choose Provider

    private var chooseProviderView: some View {
        VStack(spacing: 0) {
            // Title
            Text("Choose a provider...")
                .font(.title2)
                .fontWeight(.medium)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.horizontal, 24)
                .padding(.top, 20)
                .padding(.bottom, 8)

            // First launch explanation
            if isFirstLaunch {
                Text("Select an AI provider to enable transcription, chat, and other AI features.")
                    .font(.callout)
                    .foregroundColor(.secondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.horizontal, 24)
                    .padding(.bottom, 12)
            }

            if isLoading {
                ProgressView()
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                // Radio button list (Apple Mail style) - only show providers not yet added
                ScrollView {
                    VStack(alignment: .leading, spacing: 0) {
                        if availableCatalog.isEmpty {
                            Text("All providers have been added")
                                .foregroundColor(.secondary)
                                .padding(.vertical, 40)
                        } else {
                            ForEach(availableCatalog) { entry in
                                ProviderRadioRow(
                                    entry: entry,
                                    isSelected: selectedType == entry.type
                                ) {
                                    selectedType = entry.type
                                }
                            }
                        }
                    }
                    .padding(.horizontal, 24)
                    .padding(.vertical, 8)
                }
            }

            Divider()

            // Footer with buttons
            HStack {
                // Help button
                Button(action: {}) {
                    Image(systemName: "questionmark.circle")
                        .font(.title2)
                }
                .buttonStyle(.plain)
                .foregroundColor(.secondary)

                Spacer()

                Button("Cancel") {
                    if !isFirstLaunch {
                        dismiss()
                    }
                }
                .keyboardShortcut(.cancelAction)
                .disabled(isFirstLaunch && catalog.isEmpty)

                Button(selectedEntry?.isBuiltin == true ? "Add" : "Continue") {
                    logger.info("Button tapped, selectedEntry=\(selectedEntry?.type ?? "nil"), isBuiltin=\(selectedEntry?.isBuiltin ?? false)")
                    // For built-in providers, add directly without config step
                    if let entry = selectedEntry, entry.isBuiltin {
                        logger.info("isBuiltin=true, calling addProvider()")
                        addProvider()
                    } else {
                        logger.info("isBuiltin=false, going to step 2")
                        step = 2
                    }
                }
                .keyboardShortcut(.defaultAction)
                .disabled(selectedType == nil)
            }
            .padding(.horizontal, 20)
            .padding(.vertical, 12)
        }
    }

    // MARK: - Step 2: Configure Provider

    private var configureProviderView: some View {
        VStack(spacing: 0) {
            // Header with provider info
            HStack(spacing: 12) {
                if let entry = selectedEntry {
                    ProviderLogoView(entry: entry, size: 40)
                }

                VStack(alignment: .leading) {
                    Text(selectedEntry?.name ?? "Provider")
                        .font(.title2)
                        .fontWeight(.medium)
                    Text(selectedEntry?.description ?? "")
                        .font(.callout)
                        .foregroundColor(.secondary)
                }

                Spacer()
            }
            .padding(.horizontal, 24)
            .padding(.top, 20)
            .padding(.bottom, 16)

            Divider()

            // Configuration form
            VStack(alignment: .leading, spacing: 16) {
                if let entry = selectedEntry {
                    if entry.isLocal && !entry.isBuiltin {
                        // Local servers (not built-in): optional server URL
                        VStack(alignment: .leading, spacing: 6) {
                            Text("Server URL (optional)")
                                .font(.subheadline)
                                .fontWeight(.medium)

                            TextField(defaultServerUrl(for: entry.type), text: $serverUrl)
                                .textFieldStyle(.roundedBorder)

                            Text("Leave empty to use default: \(defaultServerUrl(for: entry.type))")
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                    } else if !entry.isLocal {
                        // Cloud providers: API key required
                        VStack(alignment: .leading, spacing: 6) {
                            Text("API Key")
                                .font(.subheadline)
                                .fontWeight(.medium)

                            SecureField("Enter your API key", text: $apiKey)
                                .textFieldStyle(.roundedBorder)

                            if let url = entry.apiKeyUrl {
                                Link("Get an API key from \(entry.name)", destination: URL(string: url)!)
                                    .font(.caption)
                            }
                        }
                    }
                    // Note: Built-in providers (isBuiltin=true) should never reach step 2
                }
            }
            .padding(.horizontal, 24)
            .padding(.vertical, 16)

            Spacer()

            Divider()

            // Footer with buttons
            HStack {
                Button("Back") {
                    step = 1
                }

                Spacer()

                Button("Add") {
                    logger.info("Step 2 Add button tapped")
                    addProvider()
                }
                .keyboardShortcut(.defaultAction)
                .disabled(isAdding || (selectedEntry?.isLocal == false && apiKey.isEmpty))
            }
            .padding(.horizontal, 20)
            .padding(.vertical, 12)
        }
    }
}

// MARK: - Helpers

extension AddProviderSheet {
    func defaultServerUrl(for type: String) -> String {
        switch type {
        case "ollama": return "http://localhost:11434"
        case "lmstudio": return "http://localhost:1234"
        default: return ""
        }
    }

    private func loadCatalog() async {
        isLoading = true
        defer { isLoading = false }

        do {
            // Load catalog and existing providers
            catalog = try await providerService.listCatalog()
            let existingProviders = try await providerService.listProviders()
            existingProviderTypes = Set(existingProviders.map { $0.providerType })

            // Pre-select first available local provider for first launch
            if isFirstLaunch, let first = availableCatalog.first(where: { $0.isLocal }) {
                selectedType = first.type
            } else if selectedType == nil, let first = availableCatalog.first {
                // Pre-select first available if nothing selected
                selectedType = first.type
            }
        } catch {
            logger.error("Load catalog failed: \(String(describing: error))")
        }
    }

    private func addProvider() {
        logger.info("addProvider() called, selectedType=\(selectedType ?? "nil")")
        guard let type = selectedType else {
            logger.warning("selectedType is nil, returning early")
            return
        }
        isAdding = true

        Task { @MainActor in
            do {
                let apiBase = serverUrl.isEmpty ? nil : serverUrl
                logger.info("Creating provider type=\(type), apiBase=\(apiBase ?? "nil")")

                let result = try await providerService.createProvider(
                    providerType: type,
                    apiBase: apiBase,
                    apiKey: apiKey.isEmpty ? nil : apiKey
                )
                logger.info("Provider created: \(result.id)")
                await onAdd()
                isAdding = false

                // Store the added provider and go to model browser
                addedProvider = result
                step = 3
            } catch {
                logger.error("Add failed: \(String(describing: error))")
                isAdding = false
            }
        }
    }

    // MARK: - Step 3: Model Browser

    private var modelLibraryView: some View {
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

    private func addModelInStep3() {
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
                logger.error("Add model failed: \(String(describing: error))")
                isAddingModel = false
            }
        }
    }
}


struct ProviderRadioRow: View {
    let entry: ProviderCatalogEntry
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
