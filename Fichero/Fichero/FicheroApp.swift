import SwiftUI

@main
struct FicheroApp: App {
    // Backend connection state - will manage Python subprocess
    @StateObject private var appState = AppState()
    @StateObject private var viewSettings = ViewSettings()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(appState)
                .environmentObject(viewSettings)
                .frame(minWidth: 800, minHeight: 500)
        }
        .windowStyle(.titleBar)
        .windowToolbarStyle(.unified(showsTitle: true))
        .commands {
            // File menu
            CommandGroup(replacing: .newItem) {
                Button("Import Files...") {
                    importFiles()
                }
                .keyboardShortcut("o", modifiers: [.command])

                Button("Import Folder...") {
                    importFolder()
                }
                .keyboardShortcut("o", modifiers: [.command, .shift])

                Divider()
            }

            // View menu - custom structure like Ulysses
            CommandMenu("View") {
                // Sidebar section
                Section("Sidebar") {
                    Button {
                        viewSettings.sidebarMode = .navigate
                    } label: {
                        Label("Navigate", systemImage: "list.bullet.indent")
                        if viewSettings.sidebarMode == .navigate {
                            Image(systemName: "checkmark")
                        }
                    }
                    .keyboardShortcut("1", modifiers: [.control, .command])

                    Button {
                        viewSettings.sidebarMode = .search
                    } label: {
                        Label("Search", systemImage: "magnifyingglass")
                    }
                    .keyboardShortcut("2", modifiers: [.control, .command])

                    Button {
                        viewSettings.sidebarMode = .chat
                    } label: {
                        Label("Chat", systemImage: "bubble.left.and.bubble.right")
                    }
                    .keyboardShortcut("3", modifiers: [.control, .command])

                    Button {
                        viewSettings.sidebarMode = .workflows
                    } label: {
                        Label("Workflows", systemImage: "arrow.triangle.branch")
                    }
                    .keyboardShortcut("4", modifiers: [.control, .command])

                    Button {
                        viewSettings.sidebarMode = .activity
                    } label: {
                        Label("Activity", systemImage: "chart.bar")
                    }
                    .keyboardShortcut("5", modifiers: [.control, .command])
                }

                Divider()

                // View modes section
                Section("View") {
                    Button {
                        viewSettings.browserViewMode = .icons
                    } label: {
                        HStack {
                            if viewSettings.browserViewMode == .icons {
                                Image(systemName: "checkmark")
                            }
                            Label("as Icons", systemImage: "square.grid.2x2")
                        }
                    }
                    .keyboardShortcut("1", modifiers: [.command])

                    Button {
                        viewSettings.browserViewMode = .list
                    } label: {
                        HStack {
                            if viewSettings.browserViewMode == .list {
                                Image(systemName: "checkmark")
                            }
                            Label("as List", systemImage: "list.bullet")
                        }
                    }
                    .keyboardShortcut("2", modifiers: [.command])

                    Button {
                        viewSettings.browserViewMode = .table
                    } label: {
                        HStack {
                            if viewSettings.browserViewMode == .table {
                                Image(systemName: "checkmark")
                            }
                            Label("as Table", systemImage: "tablecells")
                        }
                    }
                    .keyboardShortcut("3", modifiers: [.command])

                    Button {
                        viewSettings.browserViewMode = .map
                    } label: {
                        HStack {
                            if viewSettings.browserViewMode == .map {
                                Image(systemName: "checkmark")
                            }
                            Label("as Map", systemImage: "rectangle.3.group")
                        }
                    }
                    .keyboardShortcut("4", modifiers: [.command])
                }

                Divider()

                // Preview section
                Section("Preview") {
                    Button {
                        viewSettings.previewMode = .none
                    } label: {
                        HStack {
                            if viewSettings.previewMode == .none {
                                Image(systemName: "checkmark")
                            }
                            Label("None", systemImage: "rectangle")
                        }
                    }
                    .keyboardShortcut("5", modifiers: [.command])

                    Button {
                        viewSettings.previewMode = .standard
                    } label: {
                        HStack {
                            if viewSettings.previewMode == .standard {
                                Image(systemName: "checkmark")
                            }
                            Label("Standard", systemImage: "rectangle.righthalf.filled")
                        }
                    }
                    .keyboardShortcut("6", modifiers: [.command])

                    Button {
                        viewSettings.previewMode = .widescreen
                    } label: {
                        HStack {
                            if viewSettings.previewMode == .widescreen {
                                Image(systemName: "checkmark")
                            }
                            Label("Widescreen", systemImage: "rectangle.split.1x2")
                        }
                    }
                    .keyboardShortcut("7", modifiers: [.command])
                }

                Divider()

                // Quick Look
                Button {
                    viewSettings.showQuickLook.toggle()
                } label: {
                    Label("Quick Look", systemImage: "eye")
                }
                .keyboardShortcut("y", modifiers: [.command])

                Divider()

                // Image Preview Tools section
                ImagePreviewMenuCommands()

                Divider()

                // Inspector toggle
                Button {
                    viewSettings.showInspector.toggle()
                } label: {
                    Label(viewSettings.showInspector ? "Hide Inspector" : "Show Inspector",
                          systemImage: "sidebar.right")
                }
                .keyboardShortcut("i", modifiers: [.command, .option])
            }

            // Remove the default sidebar toggle since we have our own
            CommandGroup(replacing: .sidebar) { }

            // Help menu additions
            CommandGroup(replacing: .help) {
                Button("Fichero Help") {
                    // Open help
                }

                Divider()

                Button("Check for Updates...") {
                    // Check updates
                }
            }

            // App menu - Providers (after Settings)
            CommandGroup(after: .appSettings) {
                Divider()

                Button("Providers...") {
                    appState.showProvidersSettings = true
                }

                Button("Add Provider...") {
                    appState.showAddProviderFromMenu()
                }
            }
        }

        // Settings window
        Settings {
            SettingsView()
                .environmentObject(appState)
        }
    }

    // MARK: - Import Actions

    private func importFiles() {
        let panel = NSOpenPanel()
        panel.allowsMultipleSelection = true
        panel.canChooseDirectories = false
        panel.canChooseFiles = true
        panel.allowedContentTypes = [.image, .pdf, .plainText]

        if panel.runModal() == .OK {
            for url in panel.urls {
                // Will call API: POST /api/ingest/file
                print("Import file: \(url.path)")
            }
        }
    }

    private func importFolder() {
        let panel = NSOpenPanel()
        panel.allowsMultipleSelection = false
        panel.canChooseDirectories = true
        panel.canChooseFiles = false

        if panel.runModal() == .OK, let url = panel.url {
            // Will call API: POST /api/ingest/folder
            print("Import folder: \(url.path)")
        }
    }
}

// MARK: - View Settings

/// Observable settings for view configuration
@MainActor
class ViewSettings: ObservableObject {
    @Published var sidebarMode: SidebarMode = .navigate
    @Published var browserViewMode: BrowserViewMode = .icons
    @Published var previewMode: PreviewMode = .standard
    @Published var showInspector: Bool = true
    @Published var showQuickLook: Bool = false
}

enum SidebarMode: String, CaseIterable {
    case navigate
    case search
    case chat
    case workflows
    case activity
}

// BrowserViewMode is defined in BrowserView.swift

enum PreviewMode: String, CaseIterable {
    case none
    case standard   // Side by side (horizontal)
    case widescreen // Browser above preview (vertical)
}

// MARK: - App State

/// Global app state including backend connection
@MainActor
class AppState: ObservableObject {
    @Published var isBackendRunning: Bool = false
    @Published var backendError: String?
    @Published var documentCount: Int = 0
    @Published var indexedCount: Int = 0
    @Published var isCheckingBackend: Bool = true  // True while checking API

    // Provider management
    @Published var providers: [ProviderResponse] = []
    @Published var showProvidersSettings: Bool = false
    @Published var showAddProvider: Bool = false
    @Published var hasCheckedProviders: Bool = false
    @Published var isFirstLaunchProviderSetup: Bool = false  // True when showing Add Provider on first launch

    private let providerService = ProviderService()

    init() {
        // Check API health on launch
        Task {
            await checkBackendHealth()
        }
    }

    /// Check if the Python API is running
    @MainActor
    func checkBackendHealth() async {
        isCheckingBackend = true
        defer { isCheckingBackend = false }

        guard let url = URL(string: "http://127.0.0.1:8765/api/health") else {
            backendError = "Invalid API URL"
            isBackendRunning = false
            return
        }

        do {
            let (data, response) = try await URLSession.shared.data(from: url)

            guard let httpResponse = response as? HTTPURLResponse,
                  httpResponse.statusCode == 200 else {
                backendError = "API returned error status"
                isBackendRunning = false
                return
            }

            // Parse health response
            struct HealthResponse: Codable {
                let status: String
                let database: String
                let documentCount: Int

                enum CodingKeys: String, CodingKey {
                    case status, database
                    case documentCount = "document_count"
                }
            }

            let health = try JSONDecoder().decode(HealthResponse.self, from: data)
            documentCount = health.documentCount
            isBackendRunning = true
            backendError = nil
            NSLog("[AppState] Backend connected: \(health.documentCount) documents")

            // Now load providers
            await loadProviders()

        } catch let error as URLError where error.code == .cannotConnectToHost {
            backendError = "Cannot connect to API server.\n\nPlease start the API first:\n\nPYTHONPATH=src python -m fichero.api"
            isBackendRunning = false
            NSLog("[AppState] Backend not reachable: \(error)")
        } catch {
            backendError = "Failed to connect to API: \(error.localizedDescription)"
            isBackendRunning = false
            NSLog("[AppState] Backend health check failed: \(error)")
        }
    }

    func loadProviders() async {
        do {
            providers = try await providerService.listProviders()

            // On first check, if no providers configured, show Add Provider as first launch
            if !hasCheckedProviders && providers.isEmpty {
                isFirstLaunchProviderSetup = true
                showAddProvider = true
            }

            hasCheckedProviders = true
        } catch {
            NSLog("[AppState] Failed to load providers: \(error)")
            hasCheckedProviders = true
        }
    }

    /// Show Add Provider from menu (not first launch)
    func showAddProviderFromMenu() {
        isFirstLaunchProviderSetup = false
        showAddProvider = true
    }

    func refreshStats() async {
        // Will call GET /api/stats
    }

    func startBackend() async {
        // Will launch: python -m fichero serve
    }

    func stopBackend() {
        // Will terminate subprocess
    }
}

// MARK: - Settings View

struct SettingsView: View {
    @EnvironmentObject var appState: AppState

    var body: some View {
        TabView {
            GeneralSettingsView()
                .tabItem {
                    Label("General", systemImage: "gear")
                }

            ProvidersSettingsView()
                .environmentObject(appState)
                .tabItem {
                    Label("Providers", systemImage: "cpu")
                }

            BackendSettingsView()
                .tabItem {
                    Label("Backend", systemImage: "server.rack")
                }
        }
        .frame(width: 550, height: 400)
    }
}

struct GeneralSettingsView: View {
    @AppStorage("thumbnailSize") private var thumbnailSize: Double = 120
    @AppStorage("autoExtractText") private var autoExtractText: Bool = true
    @AppStorage("autoCreateEmbeddings") private var autoCreateEmbeddings: Bool = true

    var body: some View {
        Form {
            Section("Display") {
                Slider(value: $thumbnailSize, in: 80...200) {
                    Text("Thumbnail Size")
                }
            }

            Section("Ingestion") {
                Toggle("Auto-extract text from documents", isOn: $autoExtractText)
                Toggle("Auto-create search embeddings", isOn: $autoCreateEmbeddings)
            }
        }
        .padding()
    }
}

struct BackendSettingsView: View {
    @EnvironmentObject var appState: AppState
    @AppStorage("backendPort") private var backendPort: Int = 8765
    @AppStorage("backendHost") private var backendHost: String = "127.0.0.1"

    var body: some View {
        Form {
            Section("Connection") {
                TextField("Host", text: $backendHost)
                TextField("Port", value: $backendPort, format: .number)

                HStack {
                    Circle()
                        .fill(appState.isBackendRunning ? Color.green : Color.red)
                        .frame(width: 10, height: 10)

                    Text(appState.isBackendRunning ? "Connected" : "Disconnected")

                    Spacer()

                    if !appState.isBackendRunning {
                        Button("Start Backend") {
                            Task { await appState.startBackend() }
                        }
                    }
                }
            }

            Section("Statistics") {
                LabeledContent("Documents") {
                    Text("\(appState.documentCount)")
                }
                LabeledContent("Indexed") {
                    Text("\(appState.indexedCount)")
                }
            }
        }
        .padding()
    }
}

// MARK: - Providers Settings View

struct ProvidersSettingsView: View {
    @EnvironmentObject var appState: AppState
    @State private var providers: [ProviderResponse] = []
    @State private var catalog: [ProviderCatalogEntry] = []
    @State private var isLoading = true
    @State private var showAddProvider = false
    @State private var selectedProvider: ProviderResponse?

    private let providerService = ProviderService()

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
            await loadProviders()
        }
        .sheet(isPresented: $showAddProvider) {
            AddProviderSheet(onAdd: loadProviders, isFirstLaunch: false)
        }
    }

    /// Providers sorted: Apple, Ollama, LM Studio, HuggingFace, then rest alphabetically
    private var sortedProviders: [ProviderResponse] {
        providers.sorted { a, b in
            let orderA = sortOrder(a.providerType)
            let orderB = sortOrder(b.providerType)
            // If both have explicit order, use that
            if orderA < 100 && orderB < 100 {
                return orderA < orderB
            }
            // If only one has explicit order, it comes first
            if orderA < 100 { return true }
            if orderB < 100 { return false }
            // Otherwise sort alphabetically
            return a.name.localizedCaseInsensitiveCompare(b.name) == .orderedAscending
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
            NSLog("[ProvidersSettings] Failed to load: \(error)")
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
                NSLog("[ProvidersSettings] Delete failed: \(error)")
            }
        }
    }
}

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

    private let providerService = ProviderService()

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
                        SecureField("API Key", text: $apiKey)
                            .textFieldStyle(.roundedBorder)

                        HStack {
                            Button("Save Key") {
                                saveAPIKey()
                            }
                            .disabled(apiKey.isEmpty || isSaving)

                            if provider.hasApiKey {
                                Button("Remove Key", role: .destructive) {
                                    removeAPIKey()
                                }
                            }
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
            ProviderModelBrowserSheet(
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
                NSLog("[ProviderDetail] Test connection failed: \(error)")
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
            NSLog("[ProviderDetail] Load models failed: \(error)")
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
                NSLog("[ProviderDetail] Save key failed: \(error)")
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
                NSLog("[ProviderDetail] Remove key failed: \(error)")
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
                NSLog("[ProviderDetail] Delete model failed: \(error)")
            }
        }
    }
}

/// Sheet for browsing and adding models to a provider
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

/// Sheet for adding models to a provider (uses shared ModelBrowserContent)
struct ProviderModelBrowserSheet: View {
    @Environment(\.dismiss) private var dismiss
    let provider: ProviderResponse
    let onAdd: () async -> Void

    @State private var selectedModel: ModelInfo?
    @State private var isAdding = false

    // For HuggingFace, show the full browser
    @State private var selectedHFModel: HFModelInfo?

    private let providerService = ProviderService()

    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                Text("Add Model to \(provider.name)")
                    .font(.headline)
                Spacer()
                Button("Cancel") { dismiss() }
            }
            .padding()

            Divider()

            if provider.providerType == "huggingface" {
                // Use full ModelBrowserView for HuggingFace
                ModelBrowserView(
                    selectedModel: $selectedHFModel,
                    onModelSelected: { model in
                        selectedHFModel = model
                    }
                )
            } else {
                // Use shared ModelBrowserContent with selection mode
                ModelBrowserContent(
                    providerType: provider.providerType,
                    providerId: provider.id,
                    selectionMode: .select,
                    selectedModel: $selectedModel,
                    onModelAdded: {}
                )
            }

            Divider()

            // Footer
            HStack {
                Spacer()

                Button("Add Model") {
                    addModel()
                }
                .keyboardShortcut(.defaultAction)
                .disabled(isAdding || (selectedModel == nil && selectedHFModel == nil))
            }
            .padding()
        }
        .frame(width: 600, height: 600)
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
                NSLog("[ModelBrowser] Add model failed: \(error)")
            }
            isAdding = false
        }
    }
}

/// Card-style row displaying model info with costs and capabilities
struct ModelInfoRow: View {
    let model: ModelInfo
    let isSelected: Bool
    var onSelect: (() -> Void)? = nil  // Optional action when tapped

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
        .background(isSelected ? Color.accentColor.opacity(0.1) : Color(nsColor: .controlBackgroundColor))
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

/// Apple Mail style provider picker with two-step flow
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

    private let providerService = ProviderService()

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
                modelBrowserView
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
                    NSLog("[AddProvider] Button tapped, selectedEntry=\(selectedEntry?.type ?? "nil"), isBuiltin=\(selectedEntry?.isBuiltin ?? false)")
                    // For built-in providers, add directly without config step
                    if let entry = selectedEntry, entry.isBuiltin {
                        NSLog("[AddProvider] isBuiltin=true, calling addProvider()")
                        addProvider()
                    } else {
                        NSLog("[AddProvider] isBuiltin=false, going to step 2")
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
                    NSLog("[AddProvider] Step 2 Add button tapped")
                    addProvider()
                }
                .keyboardShortcut(.defaultAction)
                .disabled(isAdding || (selectedEntry?.isLocal == false && apiKey.isEmpty))
            }
            .padding(.horizontal, 20)
            .padding(.vertical, 12)
        }
    }

    // MARK: - Helpers

    private func defaultServerUrl(for type: String) -> String {
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
            NSLog("[AddProvider] Load catalog failed: \(error)")
        }
    }

    private func addProvider() {
        NSLog("[AddProvider] addProvider() called, selectedType=\(selectedType ?? "nil")")
        guard let type = selectedType else {
            NSLog("[AddProvider] selectedType is nil, returning early")
            return
        }
        isAdding = true

        Task { @MainActor in
            do {
                let apiBase = serverUrl.isEmpty ? nil : serverUrl
                NSLog("[AddProvider] Creating provider type=\(type), apiBase=\(apiBase ?? "nil")")

                let result = try await providerService.createProvider(
                    providerType: type,
                    apiBase: apiBase,
                    apiKey: apiKey.isEmpty ? nil : apiKey
                )
                NSLog("[AddProvider] Provider created: \(result.id)")
                await onAdd()
                isAdding = false

                // Store the added provider and go to model browser
                addedProvider = result
                step = 3
            } catch {
                NSLog("[AddProvider] Add failed: \(error)")
                isAdding = false
            }
        }
    }

    // MARK: - Step 3: Model Browser

    private var modelBrowserView: some View {
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
                ModelBrowserContent(
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
                NSLog("[AddProvider] Add model failed: \(error)")
                isAddingModel = false
            }
        }
    }
}

/// Selection mode for model browser
enum ModelSelectionMode {
    case immediate   // Clicking adds immediately (Add Provider flow)
    case select      // Clicking selects, parent handles adding (Add Model sheet)
}

/// Reusable model browser content (used in AddProviderSheet step 3 and ProviderModelBrowserSheet)
struct ModelBrowserContent: View {
    let providerType: String
    let providerId: String
    var selectionMode: ModelSelectionMode = .immediate
    @Binding var selectedModel: ModelInfo?
    let onModelAdded: () -> Void

    // Convenience init for immediate mode (no external selection binding needed)
    init(providerType: String, providerId: String, onModelAdded: @escaping () -> Void) {
        self.providerType = providerType
        self.providerId = providerId
        self.selectionMode = .immediate
        self._selectedModel = .constant(nil)
        self.onModelAdded = onModelAdded
    }

    // Full init for select mode
    init(providerType: String, providerId: String, selectionMode: ModelSelectionMode, selectedModel: Binding<ModelInfo?>, onModelAdded: @escaping () -> Void) {
        self.providerType = providerType
        self.providerId = providerId
        self.selectionMode = selectionMode
        self._selectedModel = selectedModel
        self.onModelAdded = onModelAdded
    }

    @State private var models: [ModelInfo] = []
    @State private var isLoading = true
    @State private var searchText = ""
    @State private var sortOrder: ModelSortOrder = .recommended
    @State private var filters = ModelFilters()

    private let providerService = ProviderService()

    private var filteredModels: [ModelInfo] {
        var result = models

        // Apply search filter
        if !searchText.isEmpty {
            result = result.filter {
                $0.modelId.localizedCaseInsensitiveContains(searchText) ||
                $0.fullName.localizedCaseInsensitiveContains(searchText)
            }
        }

        // Apply capability filters
        if filters.visionOnly { result = result.filter { $0.supportsVision } }
        if filters.reasoningOnly { result = result.filter { $0.supportsReasoning } }
        if filters.toolsOnly { result = result.filter { $0.supportsFunctionCalling } }
        if filters.audioOnly { result = result.filter { $0.supportsAudioInput || $0.supportsAudioOutput } }
        if filters.pdfOnly { result = result.filter { $0.supportsPdfInput } }
        if filters.webSearchOnly { result = result.filter { $0.supportsWebSearch } }
        if filters.batchApiOnly { result = result.filter { $0.supportsBatchApi } }

        // Apply mode filters
        if filters.embeddingsOnly { result = result.filter { $0.mode == "embedding" } }
        if filters.imageGenOnly { result = result.filter { $0.mode == "image_generation" } }
        if filters.speechOnly { result = result.filter { $0.mode == "audio_speech" } }

        // Apply sorting
        switch sortOrder {
        case .recommended:
            result.sort { a, b in
                if a.isRecommended != b.isRecommended { return a.isRecommended }
                return a.modelId.localizedCaseInsensitiveCompare(b.modelId) == .orderedAscending
            }
        case .name:
            result.sort { $0.modelId.localizedCaseInsensitiveCompare($1.modelId) == .orderedAscending }
        case .cheapest:
            result.sort { ($0.inputCostPerMillion + $0.outputCostPerMillion) < ($1.inputCostPerMillion + $1.outputCostPerMillion) }
        case .context:
            result.sort { ($0.maxInputTokens ?? 0) > ($1.maxInputTokens ?? 0) }
        }

        return result
    }

    /// Count of active filters
    private var activeFilterCount: Int {
        var count = 0
        if filters.visionOnly { count += 1 }
        if filters.reasoningOnly { count += 1 }
        if filters.toolsOnly { count += 1 }
        if filters.audioOnly { count += 1 }
        if filters.pdfOnly { count += 1 }
        if filters.webSearchOnly { count += 1 }
        if filters.batchApiOnly { count += 1 }
        if filters.embeddingsOnly { count += 1 }
        if filters.imageGenOnly { count += 1 }
        if filters.speechOnly { count += 1 }
        return count
    }

    private var hasActiveFilters: Bool { activeFilterCount > 0 }

    var body: some View {
        VStack(spacing: 0) {
            // Search bar + Sort/Filter controls
            HStack(spacing: 12) {
                // Search
                HStack {
                    Image(systemName: "magnifyingglass")
                        .foregroundColor(.secondary)
                    TextField("Search models...", text: $searchText)
                        .textFieldStyle(.plain)
                }
                .padding(8)
                .background(Color(nsColor: .controlBackgroundColor))
                .cornerRadius(6)

                // Sort picker
                Menu {
                    ForEach(ModelSortOrder.allCases, id: \.self) { order in
                        Button(action: { sortOrder = order }) {
                            HStack {
                                Text(order.rawValue)
                                if sortOrder == order {
                                    Image(systemName: "checkmark")
                                }
                            }
                        }
                    }
                } label: {
                    HStack(spacing: 4) {
                        Image(systemName: "arrow.up.arrow.down")
                        Text(sortOrder.rawValue)
                            .font(.caption)
                    }
                    .padding(.horizontal, 8)
                    .padding(.vertical, 6)
                    .background(Color(nsColor: .controlBackgroundColor))
                    .cornerRadius(6)
                }
                .menuStyle(.borderlessButton)

                // Filter menu
                Menu {
                    Section("Capabilities") {
                        Toggle("Vision", isOn: $filters.visionOnly)
                        Toggle("Reasoning", isOn: $filters.reasoningOnly)
                        Toggle("Tools/Functions", isOn: $filters.toolsOnly)
                        Toggle("Audio", isOn: $filters.audioOnly)
                        Toggle("PDF Input", isOn: $filters.pdfOnly)
                        Toggle("Web Search", isOn: $filters.webSearchOnly)
                        Toggle("Batch API", isOn: $filters.batchApiOnly)
                    }

                    Section("Mode") {
                        Toggle("Embeddings", isOn: $filters.embeddingsOnly)
                        Toggle("Image Generation", isOn: $filters.imageGenOnly)
                        Toggle("Text to Speech", isOn: $filters.speechOnly)
                    }

                    if hasActiveFilters {
                        Divider()
                        Button("Clear Filters") {
                            filters = ModelFilters()
                        }
                    }
                } label: {
                    HStack(spacing: 4) {
                        Image(systemName: hasActiveFilters ? "line.3.horizontal.decrease.circle.fill" : "line.3.horizontal.decrease.circle")
                        if hasActiveFilters {
                            Text("Filter (\(activeFilterCount))")
                                .font(.caption)
                        } else {
                            Text("Filter")
                                .font(.caption)
                        }
                    }
                    .padding(.horizontal, 8)
                    .padding(.vertical, 6)
                    .background(hasActiveFilters ? Color.accentColor.opacity(0.1) : Color(nsColor: .controlBackgroundColor))
                    .cornerRadius(6)
                }
                .menuStyle(.borderlessButton)
            }
            .padding()

            // Model list
            if isLoading {
                ProgressView()
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if filteredModels.isEmpty {
                VStack(spacing: 12) {
                    Image(systemName: "cpu")
                        .font(.system(size: 40))
                        .foregroundColor(.secondary)
                    Text("No models found")
                        .foregroundColor(.secondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                ScrollView {
                    LazyVStack(spacing: 8) {
                        ForEach(filteredModels) { model in
                            ModelInfoRow(model: model, isSelected: selectedModel?.modelId == model.modelId) {
                                handleModelTap(model)
                            }
                        }
                    }
                    .padding(.horizontal, 16)
                    .padding(.vertical, 8)
                }
            }
        }
        .task {
            await loadModels()
        }
    }

    private func handleModelTap(_ model: ModelInfo) {
        switch selectionMode {
        case .immediate:
            // Add immediately
            addModel(model)
        case .select:
            // Just select, parent will handle adding
            selectedModel = model
        }
    }

    private func loadModels() async {
        isLoading = true
        defer { isLoading = false }

        do {
            models = try await providerService.listAvailableModels(providerType: providerType)
        } catch {
            NSLog("[ModelBrowser] Load models failed: \(error)")
        }
    }

    private func addModel(_ model: ModelInfo) {
        Task {
            do {
                _ = try await providerService.addModel(
                    providerId: providerId,
                    modelId: model.modelId,
                    name: model.fullName,
                    isDefault: false
                )
                onModelAdded()
            } catch {
                NSLog("[ModelBrowser] Add model failed: \(error)")
            }
        }
    }
}

/// Apple Mail style radio row - icon + name with radio button
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

/// Displays provider logo - uses bundled image if available, SF Symbol as fallback
struct ProviderLogoView: View {
    let entry: ProviderCatalogEntry
    let size: CGFloat

    var body: some View {
        Group {
            if let logoAsset = entry.logoAsset,
               let nsImage = NSImage(named: logoAsset) {
                // Use bundled logo image
                Image(nsImage: nsImage)
                    .resizable()
                    .aspectRatio(contentMode: .fit)
            } else {
                // Fallback to SF Symbol
                Image(systemName: entry.icon)
                    .font(.system(size: size * 0.7))
                    .foregroundColor(entry.swiftUIColor)
            }
        }
        .frame(width: size, height: size)
    }
}

// MARK: - Providers Settings Sheet (for menu item)

struct ProvidersSettingsSheet: View {
    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject var appState: AppState

    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                Text("Providers")
                    .font(.headline)
                Spacer()
                Button("Done") { dismiss() }
                    .keyboardShortcut(.defaultAction)
            }
            .padding()

            Divider()

            ProvidersSettingsView()
                .environmentObject(appState)
        }
        .frame(width: 600, height: 450)
    }
}

// MARK: - Notifications

extension Notification.Name {
    static let toggleInspector = Notification.Name("toggleInspector")
}

// MARK: - Image Preview Menu Commands

struct ImagePreviewMenuCommands: View {
    @AppStorage("imagePreview.magnifierEnabled") private var magnifierEnabled = false
    @AppStorage("imagePreview.loupeEnabled") private var loupeEnabled = false
    @AppStorage("imagePreview.magnifierLocked") private var magnifierLocked = false
    @AppStorage("imagePreview.loupeMagnification") private var loupeMagnification: Double = 3.0
    @AppStorage("imagePreview.loupeSize") private var loupeSize: Double = 150.0
    @AppStorage("imagePreview.panelMagnification") private var panelMagnification: Double = 4.0
    @AppStorage("imagePreview.panelHeight") private var panelHeight: Double = 120.0

    var body: some View {
        Section("Image Preview") {
            // Magnifier panel toggle
            Button {
                magnifierEnabled.toggle()
            } label: {
                HStack {
                    if magnifierEnabled {
                        Image(systemName: "checkmark")
                    }
                    Label("Magnifier Panel", systemImage: "rectangle.bottomhalf.inset.filled")
                }
            }
            .keyboardShortcut("m", modifiers: [.command, .option])

            // Lock magnifier toggle
            Button {
                magnifierLocked.toggle()
            } label: {
                HStack {
                    if magnifierLocked {
                        Image(systemName: "checkmark")
                    }
                    Label("Lock Magnifier", systemImage: magnifierLocked ? "lock.fill" : "lock.open")
                }
            }
            .keyboardShortcut("k", modifiers: [.command, .option])
            .disabled(!magnifierEnabled)

            // Loupe toggle
            Button {
                loupeEnabled.toggle()
            } label: {
                HStack {
                    if loupeEnabled {
                        Image(systemName: "checkmark")
                    }
                    Label("Loupe", systemImage: "magnifyingglass.circle")
                }
            }
            .keyboardShortcut("l", modifiers: [.command, .option])

            Divider()

            // Loupe zoom controls
            Menu("Loupe Zoom") {
                Button("Zoom In") {
                    loupeMagnification = min(loupeMagnification * 1.25, 10.0)
                }
                .keyboardShortcut("+", modifiers: [.command, .shift])

                Button("Zoom Out") {
                    loupeMagnification = max(loupeMagnification / 1.25, 1.5)
                }
                .keyboardShortcut("-", modifiers: [.command, .shift])

                Divider()

                Button("1.5x") { loupeMagnification = 1.5 }
                Button("2x") { loupeMagnification = 2.0 }
                Button("3x") { loupeMagnification = 3.0 }
                Button("5x") { loupeMagnification = 5.0 }
                Button("8x") { loupeMagnification = 8.0 }
            }

            // Loupe size controls
            Menu("Loupe Size") {
                Button("Increase Size") {
                    loupeSize = min(loupeSize * 1.25, 400.0)
                }

                Button("Decrease Size") {
                    loupeSize = max(loupeSize / 1.25, 80.0)
                }

                Divider()

                Button("Small (100px)") { loupeSize = 100 }
                Button("Medium (150px)") { loupeSize = 150 }
                Button("Large (200px)") { loupeSize = 200 }
                Button("Extra Large (300px)") { loupeSize = 300 }

                Divider()

                Text("Tip: Drag the edge of the loupe to resize")
                    .font(.caption)
            }

            // Magnifier zoom controls
            Menu("Magnifier Zoom") {
                Button("Zoom In") {
                    panelMagnification = min(panelMagnification * 1.5, 16.0)
                }
                .keyboardShortcut("+", modifiers: [.command, .control])

                Button("Zoom Out") {
                    panelMagnification = max(panelMagnification / 1.5, 1.0)
                }
                .keyboardShortcut("-", modifiers: [.command, .control])

                Divider()

                Button("1x") { panelMagnification = 1.0 }
                Button("2x") { panelMagnification = 2.0 }
                Button("4x") { panelMagnification = 4.0 }
                Button("8x") { panelMagnification = 8.0 }
                Button("16x") { panelMagnification = 16.0 }
            }

            // Panel height controls
            Menu("Magnifier Height") {
                Button("Small (80px)") { panelHeight = 80 }
                Button("Medium (120px)") { panelHeight = 120 }
                Button("Large (180px)") { panelHeight = 180 }
                Button("Extra Large (250px)") { panelHeight = 250 }
            }
        }
    }
}
