import FicheroAPIClient
import OSLog
import SwiftUI

// swiftlint:disable:next type_body_length
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
    private let maskedKeyPlaceholder = "••••••••••••••••"

    private var isLocalProvider: Bool {
        catalogEntry?.isLocal ?? false
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
            .padding()
        }
        .task(id: provider.id) {
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
