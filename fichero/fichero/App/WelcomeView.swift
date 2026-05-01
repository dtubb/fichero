import FicheroAPIClient
import SwiftUI

// MARK: - WelcomeView

struct WelcomeView: View {
    let onCreateLibrary: () -> Void
    let onOpenLibrary: () -> Void

    var body: some View {
        VStack(spacing: 24) {
            Image(systemName: "doc.richtext")
                .font(.system(size: 64))
                .foregroundColor(.accentColor)

            Text("Welcome to Fichero")
                .font(.largeTitle)
                .fontWeight(.semibold)

            Text("Create a new library or open an existing one to get started.")
                .font(.body)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)

            HStack(spacing: 16) {
                Button(action: onCreateLibrary) {
                    Label("New Library", systemImage: "plus")
                }
                .buttonStyle(.borderedProminent)

                Button(action: onOpenLibrary) {
                    Label("Open Library", systemImage: "folder")
                }
                .buttonStyle(.bordered)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding(40)
    }
}

// MARK: - OnboardingWizardView
//
// First-launch wizard. Three screens:
//   1. Welcome — what Fichero is.
//   2. Choose where AI runs — Apple Intelligence / Local / Cloud.
//   3. Setup — varies by choice.
//
// Lives here (not its own file) per the project's "no pbxproj edit" rule:
// new .swift files under fichero/fichero/ need pbxproj entries; appending
// into an existing target file avoids the round-trip.

/// Provider category the user picks on screen 2.
enum OnboardingChoice: String, Identifiable {
    case apple
    case local
    case cloud
    var id: String { rawValue }
}

// Cloud + Local provider lists used to be hardcoded enums here. They've
// been replaced with the engine's `/providers/catalog` so the wizard
// automatically reflects every provider the engine supports — see
// `localCatalog` / `cloudCatalog` accessors on `OnboardingWizardView`.

struct OnboardingWizardView: View {
    @EnvironmentObject var appState: AppState
    @EnvironmentObject var apiClient: APIClient
    @Environment(\.dismiss) private var dismiss
    @Environment(\.openURL) private var openURL

    @State private var step: Int = 0
    @State private var choice: OnboardingChoice?

    // Catalog-driven provider state. Loaded once from `/providers/catalog`
    // and filtered per category (Apple / Local / Cloud) on the setup step.
    // The user clicks a card to set `selectedProviderType`, which is the
    // single source of truth from then on (key save, defaults, etc.).
    @State private var catalog: [Components.Schemas.ProviderCatalogResponse] = []
    @State private var isCatalogLoading: Bool = false
    @State private var selectedProviderType: String?
    @State private var apiKey: String = ""
    @State private var serverURL: String = ""

    @State private var isSaving: Bool = false
    @State private var errorMessage: String?

    // Apple Intelligence availability probe (engine returns {available, reason}).
    @State private var appleProbeState: AppleProbeState = .idle
    enum AppleProbeState { case idle, probing, available, unavailable(String) }

    // Local server connectivity check.
    @State private var localTestState: LocalTestState = .idle
    enum LocalTestState { case idle, testing, ok, failed(String) }

    /// Default for new imports. Mirrors GeneralSettingsView's
    /// @AppStorage("defaultImportMode"). Default = link.
    @AppStorage("defaultImportMode") private var defaultImportMode: String = IngestMode.link.rawValue

    var body: some View {
        VStack(spacing: 0) {
            switch step {
            case 0: welcomeStep
            case 1: chooseStep
            case 2: setupStep
            default: importModeStep
            }
        }
        .frame(width: 560, height: 560)
        .task {
            // Pre-load the catalog so when the user reaches the setup step
            // there's no "loading…" flash. AddProviderSheet does the same
            // thing (see AddProviderSheet+Helpers.loadCatalog).
            await loadCatalog()
        }
    }

    // MARK: - Catalog accessors

    /// All non-builtin local providers (Ollama, LM Studio, …). Sorted by
    /// the catalog's `sort_order`.
    private var localCatalog: [Components.Schemas.ProviderCatalogResponse] {
        catalog.filter { $0.isLocal && !$0.isBuiltin }
            .sorted { $0.sortOrder < $1.sortOrder }
    }

    /// All cloud providers. Same sort.
    private var cloudCatalog: [Components.Schemas.ProviderCatalogResponse] {
        catalog.filter { !$0.isLocal && !$0.isBuiltin }
            .sorted { $0.sortOrder < $1.sortOrder }
    }

    /// The single Apple-Intelligence catalog entry (if available).
    private var appleCatalogEntry: Components.Schemas.ProviderCatalogResponse? {
        catalog.first { $0.isBuiltin }
    }

    /// The currently-selected catalog entry, if any.
    private var selectedEntry: Components.Schemas.ProviderCatalogResponse? {
        guard let selectedProviderType else { return nil }
        return catalog.first { $0.providerType == selectedProviderType }
    }

    /// Default server URL for a local provider, mirroring AddProviderSheet's
    /// `defaultServerUrl(for:)` helper. Keep them in sync.
    private func defaultServerURL(for providerType: String) -> String {
        switch providerType {
        case "ollama": return "http://localhost:11434"
        case "lmstudio": return "http://localhost:1234"
        default: return ""
        }
    }

    /// Where to send the user when they want to install the local server. Catalog
    /// doesn't carry this, so it's a small per-type table here.
    private func installURL(for providerType: String) -> URL? {
        switch providerType {
        case "ollama": return URL(string: "https://ollama.com/download")
        case "lmstudio": return URL(string: "https://lmstudio.ai/")
        default: return nil
        }
    }


    // MARK: - Step 0: Welcome

    private var welcomeStep: some View {
        VStack(spacing: 24) {
            Spacer()
            Image(systemName: "doc.richtext")
                .font(.system(size: 64))
                .foregroundColor(.accentColor)

            Text("Welcome to Fichero")
                .font(.largeTitle)
                .fontWeight(.semibold)

            Text("Fichero is a research tool for documents. Drop in PDFs, images, or scans and use AI to transcribe, catalogue, and extract people, places, and dates.")
                .multilineTextAlignment(.center)
                .foregroundStyle(.secondary)
                .padding(.horizontal, 40)

            Spacer()

            HStack {
                Button("Set up later") { skipAndDismiss() }
                    .buttonStyle(.plain)
                    .foregroundStyle(.secondary)
                Spacer()
                Button("Continue") { step = 1 }
                    .buttonStyle(.borderedProminent)
                    .keyboardShortcut(.defaultAction)
            }
            .padding(.horizontal, 40)
            .padding(.bottom, 24)
        }
    }

    // MARK: - Step 1: Choose

    private var chooseStep: some View {
        VStack(spacing: 16) {
            VStack(spacing: 4) {
                Text("Where should AI run?")
                    .font(.title2).fontWeight(.semibold)
                Text("You can change this anytime in Settings → Models.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            .padding(.top, 28)

            VStack(spacing: 10) {
                choiceCard(
                    .cloud,
                    title: "Cloud provider",
                    badge: "Recommended",
                    blurb: "Fast. High quality. Pay per use. Your text leaves your Mac. OpenAI, Anthropic, Google, OpenRouter, and others."
                )
                choiceCard(
                    .apple,
                    title: "Apple Intelligence",
                    badge: nil,
                    blurb: "Free. Private. Runs on your Mac. Requires macOS 26+ on Apple Silicon. Note: not very good with handwritten text — use a cloud provider for that."
                )
                choiceCard(
                    .local,
                    title: "Local models",
                    badge: nil,
                    blurb: "Free. Private. Run Ollama or LM Studio on your Mac. Best with 32 GB of memory or more. You install and manage the models."
                )
            }
            .padding(.horizontal, 24)

            Spacer()

            HStack {
                Button("Back") { step = 0 }
                    .buttonStyle(.plain)
                    .foregroundStyle(.secondary)
                Spacer()
                Button("Set up later in Settings") { skipAndDismiss() }
                    .buttonStyle(.plain)
                    .foregroundStyle(.secondary)
                Button("Continue") { step = 2 }
                    .buttonStyle(.borderedProminent)
                    .keyboardShortcut(.defaultAction)
                    .disabled(choice == nil)
            }
            .padding(.horizontal, 40)
            .padding(.bottom, 24)
        }
    }

    @ViewBuilder
    private func choiceCard(_ value: OnboardingChoice, title: String, badge: String?, blurb: String) -> some View {
        let isSelected = choice == value
        Button { choice = value } label: {
            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 6) {
                    Text(title).font(.headline)
                    if let badge {
                        Text(badge)
                            .font(.caption2.weight(.semibold))
                            .padding(.horizontal, 6).padding(.vertical, 2)
                            .background(Color.accentColor.opacity(0.18), in: Capsule())
                            .foregroundStyle(Color.accentColor)
                    }
                    Spacer()
                    if isSelected {
                        Image(systemName: "checkmark.circle.fill")
                            .foregroundStyle(Color.accentColor)
                    }
                }
                Text(blurb)
                    .font(.callout)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.leading)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .padding(12)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(
                RoundedRectangle(cornerRadius: 8)
                    .fill(isSelected ? Color.accentColor.opacity(0.08) : Color(nsColor: .controlBackgroundColor))
            )
            .overlay(
                RoundedRectangle(cornerRadius: 8)
                    .stroke(isSelected ? Color.accentColor : Color.gray.opacity(0.2), lineWidth: isSelected ? 2 : 1)
            )
        }
        .buttonStyle(.plain)
    }

    // MARK: - Step 2: Setup

    @ViewBuilder
    private var setupStep: some View {
        VStack(spacing: 16) {
            VStack(spacing: 4) {
                Text(setupTitle).font(.title2).fontWeight(.semibold)
            }
            .padding(.top, 28)

            Group {
                switch choice {
                case .apple: appleSetupBody
                case .local: localSetupBody
                case .cloud: cloudSetupBody
                case .none: EmptyView()
                }
            }
            .padding(.horizontal, 24)

            Spacer()

            HStack {
                Button("Back") { step = 1 }
                    .buttonStyle(.plain)
                    .foregroundStyle(.secondary)
                Spacer()
                Button("Continue") { step = 3 }
                    .buttonStyle(.borderedProminent)
                    .keyboardShortcut(.defaultAction)
                    .disabled(!canAdvanceFromSetup)
            }
            .padding(.horizontal, 40)
            .padding(.bottom, 24)
        }
    }

    // MARK: - Step 3: Import mode

    private var importModeStep: some View {
        VStack(spacing: 16) {
            VStack(spacing: 4) {
                Text("How should Fichero handle imported files?")
                    .font(.title2).fontWeight(.semibold)
                Text("You can change this anytime in Settings → General.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            .padding(.top, 28)

            VStack(spacing: 10) {
                importModeCard(
                    .link,
                    title: IngestMode.link.displayName,
                    badge: "Recommended",
                    blurb: "Files stay where they are; Fichero just references them. No duplicates, no copies. Best for libraries that already live in folders you want to keep."
                )
                importModeCard(
                    .copy,
                    title: IngestMode.copy.displayName,
                    badge: nil,
                    blurb: "Files are duplicated into the library. The original is left untouched. Use when you want a self-contained library you can move around."
                )
                importModeCard(
                    .move,
                    title: IngestMode.move.displayName,
                    badge: nil,
                    blurb: "Files are moved into the library. The original location no longer has them. Use when you're consolidating loose files into one place."
                )
            }
            .padding(.horizontal, 24)

            if let errorMessage {
                Text(errorMessage)
                    .font(.caption)
                    .foregroundStyle(.red)
                    .padding(.horizontal, 24)
            }

            Spacer()

            HStack {
                Button("Back") { step = 2; errorMessage = nil }
                    .buttonStyle(.plain)
                    .foregroundStyle(.secondary)
                    .disabled(isSaving)
                Spacer()
                Button(isSaving ? "Saving…" : finishLabel) { Task { await finish() } }
                    .buttonStyle(.borderedProminent)
                    .keyboardShortcut(.defaultAction)
                    .disabled(isSaving || !canFinish)
            }
            .padding(.horizontal, 40)
            .padding(.bottom, 24)
        }
    }

    @ViewBuilder
    private func importModeCard(_ mode: IngestMode, title: String, badge: String?, blurb: String) -> some View {
        let isSelected = defaultImportMode == mode.rawValue
        Button { defaultImportMode = mode.rawValue } label: {
            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 6) {
                    Text(title).font(.headline)
                    if let badge {
                        Text(badge)
                            .font(.caption2.weight(.semibold))
                            .padding(.horizontal, 6).padding(.vertical, 2)
                            .background(Color.accentColor.opacity(0.18), in: Capsule())
                            .foregroundStyle(Color.accentColor)
                    }
                    Spacer()
                    if isSelected {
                        Image(systemName: "checkmark.circle.fill")
                            .foregroundStyle(Color.accentColor)
                    }
                }
                Text(blurb)
                    .font(.callout)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.leading)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .padding(12)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(
                RoundedRectangle(cornerRadius: 8)
                    .fill(isSelected ? Color.accentColor.opacity(0.08) : Color(nsColor: .controlBackgroundColor))
            )
            .overlay(
                RoundedRectangle(cornerRadius: 8)
                    .stroke(isSelected ? Color.accentColor : Color.gray.opacity(0.2), lineWidth: isSelected ? 2 : 1)
            )
        }
        .buttonStyle(.plain)
    }

    private var setupTitle: String {
        switch choice {
        case .apple: return "Apple Intelligence"
        case .local: return "Local models"
        case .cloud: return "Cloud provider"
        case .none: return ""
        }
    }

    private var finishLabel: String { choice == .apple ? "Done" : "Save & finish" }

    /// Setup step → import mode step. Need a selected provider, plus the
    /// per-category data (key for cloud, URL for local; Apple needs neither).
    private var canAdvanceFromSetup: Bool {
        guard let entry = selectedEntry else { return false }
        if entry.isBuiltin { return true }
        if entry.isLocal {
            // URL is optional in AddProviderSheet; we mirror that — leaving
            // it blank means "use the catalog default URL when saving."
            return true
        }
        // Cloud: API key required.
        return !apiKey.trimmingCharacters(in: .whitespaces).isEmpty
    }

    /// Import-mode step's finish button. Mirrors `canAdvanceFromSetup` so the
    /// finish click can't slip through if state mutated between steps.
    private var canFinish: Bool { canAdvanceFromSetup }

    private var appleSetupBody: some View {
        VStack(alignment: .leading, spacing: 12) {
            if let entry = appleCatalogEntry {
                providerHeader(entry: entry)
            }
            switch appleProbeState {
            case .idle, .probing:
                HStack(spacing: 8) {
                    ProgressView().controlSize(.small)
                    Text("Checking Apple Intelligence on this Mac…").font(.callout).foregroundStyle(.secondary)
                }
            case .available:
                Label("Ready. No API key needed.", systemImage: "checkmark.seal.fill")
                    .foregroundStyle(.green)
            case .unavailable(let reason):
                Label("Not available on this Mac", systemImage: "exclamationmark.triangle.fill")
                    .foregroundStyle(.orange)
                Text(reason).font(.caption).foregroundStyle(.secondary)
                Text("Pick a different option from the previous step, or set this up later in Settings → Models.")
                    .font(.caption).foregroundStyle(.secondary)
            }
            Text("Heads up: Apple Intelligence isn't very good with handwritten text. For old manuscripts, scanned forms, or cursive, pick a cloud provider here or in Settings later.")
                .font(.callout).foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .task(id: choice) {
            // Re-probe whenever the user lands on the Apple step. Also pin
            // selectedProviderType to the catalog's apple entry so finish()
            // has something to look at.
            guard choice == .apple else { return }
            if let apple = appleCatalogEntry { selectedProviderType = apple.providerType }
            if case .idle = appleProbeState {
                await probeAppleIntelligence()
            }
        }
    }

    /// Shared header for the Apple/Local/Cloud setup — logo + name + description
    /// driven by the catalog. Mirrors the configureProviderView header in
    /// AddProviderSheet+Step2.swift.
    @ViewBuilder
    private func providerHeader(entry: Components.Schemas.ProviderCatalogResponse) -> some View {
        HStack(spacing: 12) {
            ProviderLogoView(entry: entry, size: 36)
            VStack(alignment: .leading, spacing: 2) {
                Text(entry.name).font(.headline)
                Text(entry.description).font(.callout).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Spacer()
        }
    }

    /// One row in the catalog-driven provider list. Click to select.
    @ViewBuilder
    private func catalogRow(entry: Components.Schemas.ProviderCatalogResponse) -> some View {
        let isSelected = selectedProviderType == entry.providerType
        Button {
            selectedProviderType = entry.providerType
            // For local providers, prime the URL field with the catalog default.
            if entry.isLocal && serverURL.isEmpty {
                serverURL = defaultServerURL(for: entry.providerType)
            }
            // Reset transient state that's specific to a different provider.
            apiKey = ""
            localTestState = .idle
        } label: {
            HStack(spacing: 12) {
                Image(systemName: isSelected ? "circle.inset.filled" : "circle")
                    .foregroundStyle(isSelected ? Color.accentColor : Color.secondary)
                ProviderLogoView(entry: entry, size: 24)
                Text(entry.name).font(.callout)
                Spacer()
            }
            .padding(.vertical, 6)
            .padding(.horizontal, 8)
            .background(
                RoundedRectangle(cornerRadius: 6)
                    .fill(isSelected ? Color.accentColor.opacity(0.08) : Color.clear)
            )
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }

    private var localSetupBody: some View {
        VStack(alignment: .leading, spacing: 12) {
            if isCatalogLoading && localCatalog.isEmpty {
                HStack { ProgressView().controlSize(.small); Text("Loading…").font(.caption).foregroundStyle(.secondary) }
            }

            VStack(spacing: 2) {
                ForEach(localCatalog) { entry in
                    catalogRow(entry: entry)
                }
            }

            if let entry = selectedEntry, entry.isLocal {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Server URL").font(.caption).foregroundStyle(.secondary)
                    HStack {
                        TextField(defaultServerURL(for: entry.providerType), text: $serverURL)
                            .textFieldStyle(.roundedBorder)
                            .disableAutocorrection(true)
                            .onChange(of: serverURL) { _, _ in
                                if case .ok = localTestState { localTestState = .idle }
                                if case .failed = localTestState { localTestState = .idle }
                            }
                        Button("Test") { Task { await testLocalConnection() } }
                            .disabled({ if case .testing = localTestState { return true } else { return false } }())
                    }
                    Text("Leave empty to use \(defaultServerURL(for: entry.providerType)).")
                        .font(.caption2).foregroundStyle(.secondary)
                }

                switch localTestState {
                case .idle: EmptyView()
                case .testing:
                    HStack(spacing: 6) {
                        ProgressView().controlSize(.small)
                        Text("Testing…").font(.caption).foregroundStyle(.secondary)
                    }
                case .ok:
                    Label("Connected", systemImage: "checkmark.circle.fill")
                        .font(.caption).foregroundStyle(.green)
                case .failed(let reason):
                    Label(reason, systemImage: "exclamationmark.triangle.fill")
                        .font(.caption).foregroundStyle(.orange)
                }

                if let url = installURL(for: entry.providerType) {
                    Button { openURL(url) } label: {
                        Label("Install \(entry.name)", systemImage: "arrow.up.right.square")
                            .font(.caption)
                    }
                    .buttonStyle(.plain)
                    .foregroundStyle(Color.accentColor)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .task(id: choice) {
            // When the user lands on Local, pre-select the first available
            // entry to mirror AddProviderSheet's first-launch behavior.
            guard choice == .local, selectedProviderType == nil,
                  let first = localCatalog.first else { return }
            selectedProviderType = first.providerType
            if serverURL.isEmpty { serverURL = defaultServerURL(for: first.providerType) }
        }
    }

    private var cloudSetupBody: some View {
        VStack(alignment: .leading, spacing: 12) {
            if isCatalogLoading && cloudCatalog.isEmpty {
                HStack { ProgressView().controlSize(.small); Text("Loading…").font(.caption).foregroundStyle(.secondary) }
            }

            // Scroll the cloud list — there are 12+ providers in the catalog.
            ScrollView {
                VStack(spacing: 2) {
                    ForEach(cloudCatalog) { entry in
                        catalogRow(entry: entry)
                    }
                }
            }
            .frame(maxHeight: 180)

            if let entry = selectedEntry, !entry.isLocal, !entry.isBuiltin {
                VStack(alignment: .leading, spacing: 4) {
                    Text("API key").font(.caption).foregroundStyle(.secondary)
                    SecureField("Enter your \(entry.name) API key", text: $apiKey)
                        .textFieldStyle(.roundedBorder)
                    if let urlString = entry.apiKeyUrl, let url = URL(string: urlString) {
                        Button { openURL(url) } label: {
                            Label("Get a \(entry.name) API key", systemImage: "arrow.up.right.square")
                                .font(.caption)
                        }
                        .buttonStyle(.plain)
                        .foregroundStyle(Color.accentColor)
                    }
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .task(id: choice) {
            // Pre-select the first cloud provider (typically OpenAI) when the
            // user lands on the cloud step. Mirrors AddProviderSheet behavior.
            guard choice == .cloud, selectedProviderType == nil,
                  let first = cloudCatalog.first else { return }
            selectedProviderType = first.providerType
        }
    }

    // MARK: - Actions

    /// Load the provider catalog from the engine. Idempotent — safe to call
    /// from `.task`; subsequent calls are skipped if the catalog already loaded.
    private func loadCatalog() async {
        guard catalog.isEmpty, !isCatalogLoading else { return }
        isCatalogLoading = true
        defer { isCatalogLoading = false }
        do {
            catalog = try await appState.providerService.listCatalog()
        } catch {
            // Non-fatal — wizard falls back to its built-in copy.
            errorMessage = "Couldn't load provider list: \(error.localizedDescription)"
        }
    }

    /// Probe Apple Intelligence via the engine route — runs fm-bridge --probe
    /// (availability check only, no model warm-up). The route is also used
    /// by AISettingsView for the "Apple Intelligence not detected" badge.
    private func probeAppleIntelligence() async {
        appleProbeState = .probing
        struct Result: Decodable {
            let available: Bool
            let reason: String?
        }
        do {
            let result: Result = try await apiClient.get("/providers/apple-intelligence/probe")
            if result.available {
                appleProbeState = .available
            } else {
                appleProbeState = .unavailable(result.reason ?? "Apple Intelligence isn't available on this Mac.")
            }
        } catch {
            appleProbeState = .unavailable(
                "Couldn't check availability — \(error.localizedDescription). " +
                "You can still pick this and configure later in Settings."
            )
        }
    }

    /// Hit the local Ollama / LM Studio server with a known endpoint and check
    /// for a 200 response. Endpoint differs per provider:
    ///   - Ollama: GET /api/tags returns a (possibly empty) JSON model list.
    ///   - LM Studio: OpenAI-compatible — GET /v1/models returns the list.
    /// We probe whichever the user picked. Falls back to the catalog default
    /// URL when the user left the field empty (mirrors save behavior).
    private func testLocalConnection() async {
        guard let entry = selectedEntry, entry.isLocal else { return }
        let urlString = serverURL.trimmingCharacters(in: .whitespaces).isEmpty
            ? defaultServerURL(for: entry.providerType)
            : serverURL.trimmingCharacters(in: .whitespaces)
        guard let baseURL = URL(string: urlString) else {
            localTestState = .failed("That doesn't look like a URL.")
            return
        }
        var probeURL = baseURL
        switch entry.providerType {
        case "ollama":
            probeURL = baseURL.appendingPathComponent("api/tags")
        case "lmstudio":
            if baseURL.path.hasSuffix("/v1") {
                probeURL = baseURL.appendingPathComponent("models")
            } else {
                probeURL = baseURL.appendingPathComponent("v1/models")
            }
        default:
            // Unknown local server: just hit the base URL.
            break
        }

        localTestState = .testing
        do {
            var request = URLRequest(url: probeURL)
            request.timeoutInterval = 5
            let (_, response) = try await URLSession.shared.data(for: request)
            guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
                let code = (response as? HTTPURLResponse)?.statusCode ?? 0
                localTestState = .failed("Server responded with HTTP \(code).")
                return
            }
            localTestState = .ok
        } catch {
            localTestState = .failed("Couldn't reach \(probeURL.host ?? "server") — is \(entry.name) running?")
        }
    }

    private func skipAndDismiss() {
        // Mark complete so the wizard doesn't reappear; user can configure
        // providers anytime in Settings → Models.
        UserDefaults.standard.set(true, forKey: "hasCompletedOnboarding")
        dismiss()
    }

    private func finish() async {
        guard let entry = selectedEntry else { return }
        isSaving = true
        defer { isSaving = false }
        errorMessage = nil

        do {
            // 1. Save the provider config (skip for built-ins — Apple).
            if !entry.isBuiltin {
                let trimmedURL = serverURL.trimmingCharacters(in: .whitespaces)
                let trimmedKey = apiKey.trimmingCharacters(in: .whitespaces)
                _ = try await appState.providerService.createProvider(
                    providerType: entry.providerType,
                    name: entry.name,
                    apiBase: entry.isLocal ? (trimmedURL.isEmpty ? nil : trimmedURL) : nil,
                    apiKey: !entry.isLocal ? (trimmedKey.isEmpty ? nil : trimmedKey) : nil
                )
            }

            // 2. Apply sensible AI defaults so the user doesn't open a fresh
            //    library with empty pickers in every workflow. Same shape
            //    AISettingsView writes (`PUT /api/settings/ai-defaults`).
            //    User can refine in Settings → AI; here we just give them a
            //    working starting point keyed off the provider they picked.
            try? await applyDefaultsForChosenProvider(entry: entry)

            UserDefaults.standard.set(true, forKey: "hasCompletedOnboarding")
            dismiss()
        } catch {
            errorMessage = "Couldn't save: \(error.localizedDescription)"
        }
    }

    /// Set the chosen provider as the default for text / vision / transcription.
    /// Uses the provider's catalog `default_model` where available; otherwise
    /// leaves the model field empty so the engine's per-provider fallback kicks
    /// in. Wrapped in `try?` upstream — failure to set defaults shouldn't block
    /// onboarding from completing.
    private func applyDefaultsForChosenProvider(entry: Components.Schemas.ProviderCatalogResponse) async throws {
        // Pull current defaults so we don't blow away anything already
        // configured (e.g., if onboarding ran twice).
        var defaults = (try? await appState.fetchAIDefaults()) ?? AIDefaults()

        let providerType = entry.providerType
        let model = entry.defaultModel ?? ""

        // Text — every provider supports text.
        if defaults.textProvider.isEmpty { defaults.textProvider = providerType }
        if defaults.textModel.isEmpty { defaults.textModel = model }

        // Vision — only set when the provider claims vision support.
        if entry.supportsVision {
            if defaults.visionProvider.isEmpty { defaults.visionProvider = providerType }
            if defaults.visionModel.isEmpty { defaults.visionModel = model }
        }

        // Audio (transcription) — leave the engine's fallback to handle this
        // for providers without dedicated audio models. Setting the provider
        // here only when we know it'll work would mean a per-provider table;
        // safer to let user pick in Settings → AI → Audio if they care.

        try await appState.saveAIDefaults(defaults)
    }
}
