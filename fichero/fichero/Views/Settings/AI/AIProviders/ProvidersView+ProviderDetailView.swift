import FicheroAPIClient
import OSLog
import SwiftUI

struct ProviderDetailView: View {
    let provider: Components.Schemas.ProviderResponse
    let catalogEntry: Components.Schemas.ProviderCatalogResponse?
    let onUpdate: () async -> Void

    @State private var apiKey: String = ""
    @State private var isSaving = false

    @State private var isTesting = false
    @State private var testResult: Components.Schemas.ConnectionTestResponse?
    @State private var testError: String?

    @State private var showModelBrowser = false
    @State private var userModels: [Components.Schemas.UserModelResponse] = []
    @State private var isLoadingModels = false
    @State private var modelsLoadError: String?

    @Environment(ProviderAPIService.self) var providerService
    // The on-device catalog + runtime provisioning for a LOCAL provider now live
    // INSIDE its row (Daniel, 2026-09-05). Reached through the app-wide store so
    // the same install/progress state drives every surface.
    @Environment(AppState.self) var appState
    private let maskedKeyPlaceholder = "••••••••••••••••"

    private var isLocalProvider: Bool {
        catalogEntry?.isLocal ?? false
    }

    /// MLX is the one local runtime that needs a Python sidecar provisioned
    /// before its models can serve; its row shows the runtime block.
    private var showsRuntimeBlock: Bool {
        provider.providerType == "omlx"
    }

    /// A local runtime that answers no prompts — spaCy (grammar), Kraken (OCR),
    /// Whisper (ASR). It is in-process, not a server, so there is no connection
    /// to open and no chat model to reference: its readiness is "is the runtime/
    /// model installed", shown by the Status row + the On-Device Models section.
    ///
    /// Both of the crash-and-clutter fixes below key off this:
    /// - Test Connection is HIDDEN (Daniel: connecting to spaCy crashed the app;
    ///   a no-prompt runtime has nothing to test, and firing the connect action
    ///   at it is the crash surface — the Status row already states readiness).
    /// - the reference-model browser is HIDDEN (it opened blank for spaCy).
    private var isNoPromptRuntime: Bool {
        isLocalProvider && !(catalogEntry?.supportsChat ?? true)
    }

    /// The reference-model list ("Models" + "Add Models…" browser) applies to
    /// providers whose models you REFERENCE by id for chat/completion — cloud
    /// providers and MLX. A no-prompt local runtime has none, so it is
    /// suppressed rather than left to come up blank.
    private var usesReferenceModels: Bool {
        !isNoPromptRuntime
    }

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

                // No-prompt local runtimes (spaCy/Kraken/Whisper) have no
                // connection to test — firing the connect action at spaCy
                // crashed the app (Daniel). Readiness is the Status row above
                // plus the On-Device Models section below; no button here.
                if !isNoPromptRuntime {
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
                }

                // On-device runtime + its installable models, filtered to THIS
                // provider (MLX/spaCy/Kraken/Whisper). The downloads that used
                // to sit in a separate "MLX Runtime" block below the provider
                // list now live in the provider's own row.
                if isLocalProvider {
                    LocalRuntimeModelsView(
                        store: appState.localInferenceStore,
                        providerType: provider.providerType,
                        showRuntime: showsRuntimeBlock,
                        showServices: showsRuntimeBlock,
                        modelsTitle: "On-Device Models",
                        hidesEmptyCatalog: !showsRuntimeBlock
                    )
                }

                if !isLocalProvider {
                    Section("API Key") {
                        if provider.hasApiKey {
                            HStack {
                                Image(systemName: "key.fill")
                                    .foregroundColor(.green)
                                Text("API key saved in Keychain")
                                    .foregroundColor(.secondary)
                                Spacer()
                            }

                            // #934 — SecureField in a macOS Form treats
                            // its label parameter as a leading-label,
                            // which rendered the masked dots floating to
                            // the LEFT of the input box (the user: \"is not
                            // showing the key properly, it's to the left
                            // of the text box\"). Use an empty label +
                            // `prompt:` so the dots appear INSIDE the
                            // field as placeholder text — the intent.
                            SecureField(
                                "", text: $apiKey,
                                prompt: Text(maskedKeyPlaceholder)
                                    .foregroundStyle(.secondary)
                            )
                            .textFieldStyle(.roundedBorder)
                            .labelsHidden()

                            Text("Enter a new key to replace the saved one")
                                .font(.caption)
                                .foregroundColor(.secondary)

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
                            Text("No API key configured")
                                .foregroundColor(.orange)

                            // Same labels-on-left issue as the saved-key
                            // branch; same fix. (#934)
                            SecureField(
                                "", text: $apiKey,
                                prompt: Text("Enter your API key")
                                    .foregroundStyle(.secondary)
                            )
                            .textFieldStyle(.roundedBorder)
                            .labelsHidden()

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

                if usesReferenceModels {
                Section {
                    if isLoadingModels {
                        ProgressView("Loading models...")
                    } else if let modelsLoadError {
                        VStack(alignment: .leading, spacing: 8) {
                            HStack(spacing: 6) {
                                Image(systemName: "exclamationmark.triangle.fill")
                                    .foregroundColor(.orange)
                                Text("Couldn't load models")
                            }
                            Text(modelsLoadError)
                                .font(.caption)
                                .foregroundColor(.secondary)
                            Button("Retry") {
                                Task { await loadModels() }
                            }
                        }
                    } else if userModels.isEmpty {
                        VStack(alignment: .leading, spacing: 8) {
                            Text("No models configured")
                                .foregroundColor(.secondary)
                            Button {
                                showModelBrowser = true
                            } label: {
                                Label("Add Models…", systemImage: "plus.circle")
                            }
                        }
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

                                HStack(spacing: 4) {
                                    ForEach(model.capabilities, id: \.self) { cap in
                                        capabilityBadge(cap)
                                    }
                                }

                                Button {
                                    deleteModel(model)
                                } label: {
                                    Image(systemName: "minus.circle")
                                        .foregroundColor(.red)
                                }
                                .buttonStyle(.plain)
                                // Names its row: every model in this list has the
                                // same icon, so a bare "Remove" is announced
                                // identically for all of them.
                                .accessibilityLabel("Remove model \(model.name)")
                            }
                            .padding(.vertical, 2)
                        }

                        Button {
                            showModelBrowser = true
                        } label: {
                            Label("Add Models…", systemImage: "plus.circle")
                        }
                    }
                } header: {
                    HStack {
                        Text("Models")
                        Spacer()
                        Button {
                            showModelBrowser = true
                        } label: {
                            Image(systemName: "plus")
                        }
                        .buttonStyle(.plain)
                        .accessibilityLabel("Add Models")
                        .help("Add Models")
                    }
                }
                }
            }
            .padding()
        }
        .task(id: provider.id) {
            await loadModels()
            // Populate the on-device catalog/runtime for local provider rows.
            // The store guards against concurrent loads, so this is safe to
            // call from every local row's task.
            if isLocalProvider {
                await appState.localInferenceStore.load()
            }
        }
        .sheet(isPresented: $showModelBrowser) {
            AIProviderAddModelsSheet(
                provider: provider,
                onAdd: loadModels
            )
        }
    }
}

// MARK: - Badges & actions

extension ProviderDetailView {
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

    func testConnection() {
        isTesting = true
        testResult = nil
        testError = nil

        Task {
            do {
                testResult = try await providerService.testConnection(providerType: provider.providerType)
            } catch {
                testError = error.localizedDescription
                providersViewLogger.error("Test connection failed: \(String(describing: error))")
            }
            isTesting = false
        }
    }

    private func loadModels() async {
        isLoadingModels = true
        userModels = []
        modelsLoadError = nil
        defer { isLoadingModels = false }

        do {
            userModels = try await providerService.listProviderModels(providerId: provider.id)
        } catch {
            providersViewLogger.error("Load models failed: \(String(describing: error))")
            modelsLoadError = error.localizedDescription
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
                providersViewLogger.error("Save key failed: \(String(describing: error))")
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
                providersViewLogger.error("Remove key failed: \(String(describing: error))")
            }
        }
    }

    private func deleteModel(_ model: Components.Schemas.UserModelResponse) {
        Task {
            do {
                try await providerService.removeModel(providerId: provider.id, modelId: model.id)
                await loadModels()
            } catch {
                providersViewLogger.error("Delete model failed: \(String(describing: error))")
            }
        }
    }
}
