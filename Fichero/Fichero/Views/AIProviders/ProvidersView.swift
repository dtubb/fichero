import SwiftUI
import OSLog

private let logger = Logger(subsystem: "ca.tubb.Fichero", category: "ProvidersView")

/// Providers management view - manage LLM providers and their models
struct ProvidersView: View {
    @EnvironmentObject var appState: AppState
    @State private var providers: [ProviderResponse] = []
    @State private var catalog: [ProviderCatalogEntry] = []
    @State private var isLoading = true
    @State private var showAddProvider = false
    @State private var selectedProvider: ProviderResponse?

    @EnvironmentObject var providerService: ProviderService

    var body: some View {
        HSplitView {
            // Provider list (left)
            VStack(alignment: .leading, spacing: 0) {
                List(selection: $selectedProvider) {
                    ForEach(sortedProviders) { provider in
                        ProviderSettingsRow(
                            provider: provider,
                            catalogEntry: catalog.first { $0.type == provider.providerType }
                        )
                        .tag(provider)
                    }
                }
                .listStyle(.sidebar)

                Divider()

                // Add/Remove buttons
                HStack(spacing: 4) {
                    Button(action: { showAddProvider = true }) {
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

            // Provider details (right)
            if let provider = selectedProvider {
                ProviderDetailView(
                    provider: provider,
                    catalogEntry: catalog.first { $0.type == provider.providerType },
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

    /// Providers sorted: Apple, Ollama, LM Studio, HuggingFace, then rest alphabetically
    private var sortedProviders: [ProviderResponse] {
        providers.sorted { provider1, provider2 in
            let orderA = sortOrder(provider1.providerType)
            let orderB = sortOrder(provider2.providerType)
            // If both have explicit order, use that
            if orderA < 100 && orderB < 100 {
                return orderA < orderB
            }
            // If only one has explicit order, it comes first
            if orderA < 100 { return true }
            if orderB < 100 { return false }
            // Otherwise sort alphabetically
            return provider1.name.localizedCaseInsensitiveCompare(provider2.name) == .orderedAscending
        }
    }

    private func sortOrder(_ type: String) -> Int {
        switch type {
        case "apple_vision": return 0
        case "apple_intelligence": return 1
        case "ollama": return 2
        case "lmstudio": return 3
        case "huggingface": return 4
        default: return 100  // Sort alphabetically
        }
    }

    private func loadProviders() async {
        isLoading = true
        defer { isLoading = false }

        do {
            providers = try await providerService.listProviders()
            catalog = try await providerService.listCatalog()
        } catch {
            logger.error("Failed to load: \(String(describing: error))")
        }
    }

    private func deleteSelectedProvider() {
        guard let provider = selectedProvider else { return }
        Task {
            do {
                try await providerService.deleteProvider(provider.id)
                selectedProvider = nil
                await loadProviders()
            } catch {
                logger.error("Delete failed: \(String(describing: error))")
            }
        }
    }
}

/// Provider row in the settings list
struct ProviderSettingsRow: View {
    let provider: ProviderResponse
    let catalogEntry: ProviderCatalogEntry?

    /// Whether this provider is local (always shows green status)
    private var isLocalProvider: Bool {
        catalogEntry?.isLocal ?? false
    }

    var body: some View {
        HStack(spacing: 10) {
            // Provider logo (actual logo from catalog or SF Symbol fallback)
            if let entry = catalogEntry {
                ProviderLogoView(entry: entry, size: 28)
            } else {
                // Fallback SF Symbol
                ZStack {
                    RoundedRectangle(cornerRadius: 4)
                        .fill(Color.accentColor.opacity(0.15))
                        .frame(width: 28, height: 28)

                    Image(systemName: "cpu")
                        .font(.caption)
                        .foregroundColor(.accentColor)
                }
            }

            VStack(alignment: .leading, spacing: 1) {
                Text(provider.name)
                    .font(.body)

                Text(provider.providerType)
                    .font(.caption)
                    .foregroundColor(.secondary)
            }

            Spacer()

            // Status - green for local providers or those with API key
            Circle()
                .fill(isLocalProvider || provider.hasApiKey ? Color.green : Color.orange)
                .frame(width: 8, height: 8)
        }
        .padding(.vertical, 2)
    }
}

/// Provider detail view showing configuration and models
struct ProviderDetailView: View {
    let provider: ProviderResponse
    let catalogEntry: ProviderCatalogEntry?  // For checking isLocal/isBuiltin
    let onUpdate: () async -> Void

    @State private var apiKey: String = ""
    @State private var isSaving = false

    // Connection test state
    @State private var isTesting = false
    @State private var testResult: ConnectionTestResponse?
    @State private var testError: String?

    // Models state
    @State private var showModelBrowser = false
    @State private var userModels: [UserModelResponse] = []
    @State private var isLoadingModels = false

    @EnvironmentObject var providerService: ProviderService

    /// Whether this provider is local (no API key needed)
    private var isLocalProvider: Bool {
        catalogEntry?.isLocal ?? false
    }

    /// Status text based on provider type
    private var statusText: String {
        if isLocalProvider {
            return catalogEntry?.isBuiltin == true ? "Built-in" : "Local"
        }
        return provider.hasApiKey ? "Configured" : "Needs API Key"
    }

    var body: some View {
        ScrollView {
            Form {
                Section("Provider") {
                    LabeledContent("Name") {
                        Text(provider.name)
                    }
                    LabeledContent("Type") {
                        Text(provider.providerType)
                    }
                    LabeledContent("Status") {
                        HStack {
                            Circle()
                                .fill(isLocalProvider || provider.hasApiKey ? Color.green : Color.orange)
                                .frame(width: 8, height: 8)
                            Text(statusText)
                        }
                    }
                }

                // Connection Test Section
                Section("Connection") {
                    HStack {
                        Button(action: testConnection) {
                            HStack(spacing: 6) {
                                if isTesting {
                                    ProgressView()
                                        .scaleEffect(0.7)
                                } else {
                                    Image(systemName: "network")
                                }
                                Text("Test Connection")
                            }
                        }
                        .disabled(isTesting)

                        Spacer()

                        // Show test result
                        if let result = testResult {
                            HStack(spacing: 4) {
                                Image(systemName: result.success ? "checkmark.circle.fill" : "xmark.circle.fill")
                                    .foregroundColor(result.success ? .green : .red)
                                if let latency = result.latencyMs {
                                    Text(String(format: "%.0fms", latency))
                                        .font(.caption)
                                        .foregroundColor(.secondary)
                                }
                            }
                        } else if let error = testError {
                            HStack(spacing: 4) {
                                Image(systemName: "exclamationmark.triangle.fill")
                                    .foregroundColor(.orange)
                                Text("Error")
                                    .font(.caption)
                                    .foregroundColor(.secondary)
                            }
                            .help(error)
                        }
                    }

                    if let result = testResult {
                        Text(result.message)
                            .font(.caption)
                            .foregroundColor(result.success ? .secondary : .red)

                        if let model = result.modelTested {
                            Text("Model: \(model)")
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                    }
                }

                // Only show API Key section for cloud providers
                if !isLocalProvider {
                    Section("API Key") {
                        if provider.hasApiKey {
                            // Key exists - show status and option to replace
                            HStack {
                                Image(systemName: "key.fill")
                                    .foregroundColor(.green)
                                Text("API key saved in Keychain")
                                    .foregroundColor(.secondary)
                                Spacer()
                            }

                            SecureField("Enter new key to replace", text: $apiKey)
                                .textFieldStyle(.roundedBorder)

                            HStack {
                                Button("Replace Key") {
                                    saveAPIKey()
                                }
                                .disabled(apiKey.isEmpty || isSaving)

                                Button("Remove Key", role: .destructive) {
                                    removeAPIKey()
                                }
                            }
                        } else {
                            // No key - show input field
                            Text("No API key configured")
                                .foregroundColor(.orange)

                            SecureField("Enter your API key", text: $apiKey)
                                .textFieldStyle(.roundedBorder)

                            Button("Save Key") {
                                saveAPIKey()
                            }
                            .disabled(apiKey.isEmpty || isSaving)
                        }

                        Text("Keys are stored securely in macOS Keychain")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                }

                // Models Section
                Section {
                    if isLoadingModels {
                        ProgressView("Loading models...")
                    } else if userModels.isEmpty {
                        Text("No models configured")
                            .foregroundColor(.secondary)
                    } else {
                        ForEach(userModels) { model in
                            HStack {
                                VStack(alignment: .leading, spacing: 2) {
                                    HStack {
                                        Text(model.name)
                                            .font(.body)
                                        if model.isDefault {
                                            Text("Default")
                                                .font(.caption2)
                                                .padding(.horizontal, 4)
                                                .padding(.vertical, 1)
                                                .background(Color.accentColor.opacity(0.2))
                                                .cornerRadius(3)
                                        }
                                    }
                                    Text(model.modelId)
                                        .font(.caption)
                                        .foregroundColor(.secondary)
                                }

                                Spacer()

                                // Capabilities badges
                                HStack(spacing: 4) {
                                    ForEach(model.capabilities, id: \.self) { cap in
                                        capabilityBadge(cap)
                                    }
                                }

                                // Delete button
                                Button(action: { deleteModel(model) }) {
                                    Image(systemName: "minus.circle")
                                        .foregroundColor(.red)
                                }
                                .buttonStyle(.plain)
                            }
                            .padding(.vertical, 2)
                        }
                    }
                } header: {
                    HStack {
                        Text("Models")
                        Spacer()
                        Button(action: { showModelBrowser = true }) {
                            Image(systemName: "plus")
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
            .padding()
        }
        .task(id: provider.id) {
            // Reload models when provider changes
            await loadModels()
        }
        .sheet(isPresented: $showModelBrowser) {
            AIProviderAddModelsSheet(
                provider: provider,
                onAdd: loadModels
            )
        }
    }

    @ViewBuilder
    private func capabilityBadge(_ capability: String) -> some View {
        let (icon, color): (String, Color) = {
            switch capability {
            case "vision": return ("eye", .purple)
            case "chat": return ("bubble.left.and.bubble.right", .blue)
            case "embeddings": return ("square.stack.3d.up", .green)
            case "tools": return ("wrench.and.screwdriver", .orange)
            default: return ("cpu", .gray)
            }
        }()

        Image(systemName: icon)
            .font(.caption2)
            .foregroundColor(color)
            .help(capability.capitalized)
    }

    private func testConnection() {
        isTesting = true
        testResult = nil
        testError = nil

        Task {
            do {
                testResult = try await providerService.testConnection(providerType: provider.providerType)
            } catch {
                testError = error.localizedDescription
                logger.error("Test connection failed: \(String(describing: error))")
            }
            isTesting = false
        }
    }

    private func loadModels() async {
        isLoadingModels = true
        userModels = []  // Clear immediately to avoid showing stale data
        defer { isLoadingModels = false }

        do {
            userModels = try await providerService.listProviderModels(providerId: provider.id)
        } catch {
            logger.error("Load models failed: \(String(describing: error))")
        }
    }

    private func saveAPIKey() {
        isSaving = true
        Task {
            do {
                try await providerService.setAPIKey(providerType: provider.providerType, apiKey: apiKey)
                apiKey = ""
                await onUpdate()
            } catch {
                logger.error("Save key failed: \(String(describing: error))")
            }
            isSaving = false
        }
    }

    private func removeAPIKey() {
        Task {
            do {
                try await providerService.deleteAPIKey(providerType: provider.providerType)
                await onUpdate()
            } catch {
                logger.error("Remove key failed: \(String(describing: error))")
            }
        }
    }

    private func deleteModel(_ model: UserModelResponse) {
        Task {
            do {
                // Use model.id (UUID), not model.modelId (the model name like "gemini-1.0-pro")
                try await providerService.removeModel(providerId: provider.id, modelId: model.id)
                await loadModels()
            } catch {
                logger.error("Delete model failed: \(String(describing: error))")
            }
        }
    }
}

/// Sort options for model list
enum ModelSortOrder: String, CaseIterable {
    case recommended = "Recommended"
    case name = "Name"
    case cheapest = "Cheapest"
    case context = "Context Size"
}

/// Filter options for model capabilities
struct ModelFilters {
    // Capabilities
    var visionOnly = false
    var reasoningOnly = false
    var toolsOnly = false
    var audioOnly = false
    var pdfOnly = false
    var webSearchOnly = false
    var batchApiOnly = false
    // Modes
    var embeddingsOnly = false
    var imageGenOnly = false
    var speechOnly = false
}
