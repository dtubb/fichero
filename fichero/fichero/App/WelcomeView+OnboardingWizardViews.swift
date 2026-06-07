import FicheroAPIClient
import OSLog
import SwiftUI

extension OnboardingWizardView {

    // MARK: - Step 0: Welcome

    var welcomeStep: some View {
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

    var chooseStep: some View {
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
    func choiceCard(_ value: OnboardingChoice, title: String, badge: String?, blurb: String) -> some View {
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
    var setupStep: some View {
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

    var importModeStep: some View {
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
    func importModeCard(_ mode: IngestMode, title: String, badge: String?, blurb: String) -> some View {
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

    var setupTitle: String {
        switch choice {
        case .apple: return "Apple Intelligence"
        case .local: return "Local models"
        case .cloud: return "Cloud provider"
        case .none: return ""
        }
    }

    var finishLabel: String { choice == .apple ? "Done" : "Save & finish" }

    /// Setup step → import mode step. Need a selected provider, plus the
    /// per-category data (key for cloud, URL for local; Apple needs neither).
    var canAdvanceFromSetup: Bool {
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
    var canFinish: Bool { canAdvanceFromSetup }

    var appleSetupBody: some View {
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
    func providerHeader(entry: Components.Schemas.ProviderCatalogResponse) -> some View {
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
    func catalogRow(entry: Components.Schemas.ProviderCatalogResponse) -> some View {
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

    var localSetupBody: some View {
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
                                if case .connected = localTestState { localTestState = .idle }
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
                case .connected(let note):
                    Label(note ?? "Connected", systemImage: note == nil
                        ? "checkmark.circle.fill" : "exclamationmark.circle.fill")
                        .font(.caption).foregroundStyle(note == nil ? .green : .yellow)
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

    var cloudSetupBody: some View {
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
}
