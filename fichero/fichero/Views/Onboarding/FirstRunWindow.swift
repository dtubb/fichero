#if canImport(AppKit)
import AppKit
#endif
import SwiftUI

struct FirstRunWindow: View {
    @Environment(AppState.self) var appState
    @Environment(\.dismiss) private var dismiss
    /// The project's import path, for setup's Add a Folder…; absent where no project is open.
    @Environment(ImportService.self) var importService: ImportService?
    private let featureManager = FeatureManager.shared
    @State private var libraryManager = LibraryManager.shared

    @State private var step: FirstRunStep
    @State private var selectedLibraryName: String?
    @State private var documentsPermission = false
    /// "Choose a Provider" on the AI step no longer ends the flow (the recipe
    /// steps follow it); the Add Provider sheet opens when the flow finishes.
    @State private var wantsProviderSetup = false

    /// The PLATFORM's step list (#2807): the Mac runs the full flow; companion
    /// platforms (iPhone/iPad — no local engine) skip the Mac-only
    /// Library/Permissions/Cloud steps, so Welcome finishes straight into the
    /// companion connect flow (`RemoteConnectionSetupView`).
    /// Set Up… from the Inspector runs only `FirstRunStep.setUpSteps`: the same
    /// recipe steps, one code path (`source.onboard.set-up-later`).
    private let steps: [FirstRunStep]
    /// True for Set Up… (an existing library): finishing it does not mark first
    /// run complete.
    private let isSetUp: Bool

    init(setUp: Bool = false) {
        let steps = setUp
            ? FirstRunStep.setUpSteps
            : FirstRunStep.steps(isCompanionPlatform: FirstRunStep.isCompanionPlatform)
        self.steps = steps
        self.isSetUp = setUp
        _step = State(initialValue: steps.first ?? .welcome)
    }

    var body: some View {
        HStack(spacing: 0) {
            sidebar
            Divider()
            content
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        // The fixed two-pane card is a desktop window size; a compact companion
        // presentation sizes to its sheet instead (#2807).
        #if os(macOS)
        .frame(width: 760, height: 520)
        #endif
        .onAppear { surfaceDefaultLibrary() }
        // Reopen where the person left off: the project's saved answers and
        // recipe (GET /api/recipes/project).
        .task { await appState.recipeSetupStore.loadSaved() }
    }

    /// Advance within the platform step list; the LAST step finishes (#2807).
    private func advance() {
        let store = appState.recipeSetupStore
        // Start records the first yes; the window closes only when the engine kept it.
        if step == .start {
            Task { if await store.start() { finish() } }
            return
        }
        if step == steps.last {
            finish()
            return
        }
        let next = step.next(in: steps)
        // Leaving a setup screen keeps the answers so far as a draft on the
        // project, so setup can be closed at any screen; saving is not Start.
        // The next screen opens once the engine has the draft (Start plans from it).
        guard step.savesDraft else { step = next; return }
        Task {
            await store.save()
            step = next
        }
    }

    /// #2715 — A new user already lands in a working state: the app-managed
    /// "Local" library (~/Library/Application Support/Fichero/global.fichero) is
    /// always loaded by `LibraryManager` and auto-assigned to the window. Surface
    /// it here so library setup reads as optional, not a blocking step.
    private func surfaceDefaultLibrary() {
        if selectedLibraryName == nil {
            selectedLibraryName = libraryManager.globalLibrary?.displayName
        }
    }

    private var sidebar: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Fichero")
                .font(.title2.weight(.semibold))
                .padding(.bottom, 12)

            ForEach(steps) { item in
                Button {
                    step = item
                } label: {
                    Label(item.title, systemImage: item.icon)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(.vertical, 7)
                        .padding(.horizontal, 8)
                        .background(
                            RoundedRectangle(cornerRadius: 8)
                                .fill(step == item ? Color.accentColor.opacity(0.14) : Color.clear)
                        )
                }
                .buttonStyle(.plain)
            }

            Spacer()
        }
        .padding(20)
        .frame(width: 220)
        .background(Color(platformColor: .controlBackgroundColor))
    }
}

// MARK: - Content & builders
extension FirstRunWindow {
    @ViewBuilder
    private var content: some View {
        switch step {
        case .welcome:
            stepPage(
                title: "Welcome to Fichero",
                subtitle: "A research workspace for scanned sources, PDFs, notes, and knowledge graphs.",
                systemImage: "doc.richtext"
            ) {
                firstRunCard(
                    FirstRunCardConfig(
                        icon: "books.vertical",
                        title: "You're ready to go",
                        body: "Fichero already set up a local project so you can start right away. "
                            + "Customize it later — or just begin importing scans, PDFs, notes, and graphs.",
                        primaryTitle: "Get Started",
                        primaryIcon: "arrow.right",
                        primaryAction: { advance() }
                    ),
                    footer: {
                        HStack(spacing: 8) {
                            detailPill("Local-first", icon: "desktopcomputer")
                            detailPill("Knowledge graph ready", icon: "point.3.connected.trianglepath.dotted")
                            // Surface the Research workspace at first run so it's
                            // discoverable — it lives behind the flask icon in the
                            // sidebar mode bar (⌃⌘8). (#1499)
                            detailPill("Research workspace (⌃⌘8)", icon: "flask")
                        }
                    }
                )
            }
        case .library:
            stepPage(
                title: "Project",
                subtitle: "You already have a working project. Add another only if you want to.",
                systemImage: "folder"
            ) {
                firstRunCard(
                    FirstRunCardConfig(
                        icon: "folder.badge.gearshape",
                        title: "Your working project",
                        body: selectedLibraryName.map {
                            "Ready to use: \($0). You can create more projects anytime, "
                                + "or save this one to a folder of your choice from the File menu."
                        }
                            ?? "A local project is ready to use. Create more projects anytime from the File menu.",
                        primaryTitle: "Continue",
                        primaryIcon: "arrow.right",
                        primaryAction: { advance() }
                    ),
                    footer: {
                        // #2716 — "Open Existing" lives in File ▸ Open Library (⌘O)
                        // and Settings, not in first-run onboarding. Keep this step
                        // focused on the ready-to-use default library.
                        if let selectedLibraryName {
                            Label(selectedLibraryName, systemImage: "checkmark.circle.fill")
                                .foregroundStyle(.green)
                                .lineLimit(1)
                        }
                    }
                )
            }
        case .permissions:
            stepPage(
                title: "Permissions",
                subtitle: "Grant access only to the locations Fichero should work with.",
                systemImage: "lock.shield"
            ) {
                firstRunCard(
                    FirstRunCardConfig(
                        icon: documentsPermission ? "checkmark.shield" : "lock.shield",
                        title: "Authorize source locations",
                        body: documentsPermission
                            ? "Folder access is ready. That's the only permission Fichero needs to get started."
                            : "Grant folder access only for the locations Fichero should scan and organize.",
                        primaryTitle: documentsPermission ? "Continue" : "Choose Folder",
                        primaryIcon: documentsPermission ? "arrow.right" : "folder.badge.gearshape",
                        primaryAction: {
                            if documentsPermission {
                                advance()
                            } else {
                                requestDocumentsAccess()
                            }
                        }
                    ),
                    footer: {
                        // #2717 — Folder access is the only permission Fichero needs.
                        // The app declares no Accessibility entitlement (removed) and
                        // no Photos usage string; Photos is requested at import time
                        // only, never up front.
                        if documentsPermission {
                            detailPill("Documents ready", icon: "checkmark.circle.fill")
                        }
                    }
                )
            }
        case .cloud:
            stepPage(
                title: "AI is optional",
                subtitle: "Fichero is local-first. Add a provider only when you want AI.",
                systemImage: "brain"
            ) {
                firstRunCard(
                    FirstRunCardConfig(
                        icon: "cpu",
                        title: "Choose an AI provider",
                        body: "Run models on-device for free with Apple Intelligence, Ollama, or "
                            + "LM Studio, or connect a cloud provider — OpenRouter is an easy default, "
                            + "and OpenAI, Anthropic, or Google work too. Pick your default models; "
                            + "everything is optional and changeable in Settings.",
                        primaryTitle: "Choose a Provider",
                        primaryIcon: "plus",
                        primaryAction: {
                            wantsProviderSetup = true
                            advance()
                        }
                    ),
                    footer: {
                        // #2718 — local-first, provider-agnostic. Defer to the existing
                        // Add Provider flow (full catalog + default-model selection),
                        // which pre-selects a local provider on first launch. No single
                        // provider is centered.
                        VStack(alignment: .leading, spacing: 10) {
                            // #3121 — surface the zero-cloud on-device options with
                            // their TRUE availability so a fresh user can pick a
                            // private setup knowingly.
                            localFirstAIOptions
                            Text("Prefer to decide later? Skip — you can add providers anytime in Settings.")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }
                )
            }
        case .purpose:
            recipeStepPage(.purpose)
        case .material, .about, .recipe:
            recipeStepPage(step)
        case .start:
            recipeStepPage(.start)
        }
    }

    func stepPage<Content: View>(
        title: String,
        subtitle: String,
        systemImage: String,
        @ViewBuilder body: () -> Content
    ) -> some View {
        VStack(alignment: .leading, spacing: 20) {
            HStack(spacing: 12) {
                Image(systemName: systemImage)
                    .font(.title2)
                    .foregroundStyle(Color.accentColor)
                    .frame(width: 42, height: 42)
                VStack(alignment: .leading, spacing: 3) {
                    Text(title)
                        .font(.title.weight(.semibold))
                    Text(subtitle)
                        .foregroundStyle(.secondary)
                }
            }

            body()

            Spacer()
            HStack {
                Button("Skip") { finish() }
                    .buttonStyle(.plain)
                    .foregroundStyle(.secondary)
                Spacer()
                Button("Back") { step = step.previous(in: steps) }
                    .disabled(step == steps.first)
                Button(step == .start ? "Start" : step == steps.last ? "Finish" : "Continue") {
                    advance()
                }
                .disabled(step == .start && !appState.recipeSetupStore.canStart)
                .buttonStyle(.borderedProminent)
                .keyboardShortcut(.defaultAction)
            }
        }
        .padding(28)
    }

    private func firstRunCard<Footer: View>(_ config: FirstRunCardConfig, @ViewBuilder footer: () -> Footer) -> some View {
        VStack(alignment: .leading, spacing: 18) {
            Image(systemName: config.icon)
                .font(.largeTitle.weight(.semibold))
                .foregroundStyle(Color.accentColor)
                .frame(width: 64, height: 64)
                .background(Color.accentColor.opacity(0.12), in: RoundedRectangle(cornerRadius: 14))

            VStack(alignment: .leading, spacing: 8) {
                Text(config.title)
                    .font(.title3.weight(.semibold))
                Text(config.body)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }

            footer()

            Spacer()

            Button(action: config.primaryAction) {
                Label(config.primaryTitle, systemImage: config.primaryIcon)
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.borderedProminent)
        }
        .padding(22)
        .frame(maxWidth: .infinity, minHeight: 280, alignment: .leading)
        .background(Color(platformColor: .textBackgroundColor), in: RoundedRectangle(cornerRadius: 12))
        .overlay {
            RoundedRectangle(cornerRadius: 12)
                .stroke(Color.primary.opacity(0.08), lineWidth: 1)
        }
        .shadow(color: Color.black.opacity(0.04), radius: 12, x: 0, y: 4)
    }

    private func detailPill(_ title: String, icon: String) -> some View {
        Label(title, systemImage: icon)
            .font(.caption)
            .foregroundStyle(.secondary)
            .lineLimit(1)
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
            .background(Color.primary.opacity(0.05), in: RoundedRectangle(cornerRadius: 8))
    }

    private func requestDocumentsAccess() {
        #if os(macOS)
        let panel = NSOpenPanel()
        panel.canChooseFiles = false
        panel.canChooseDirectories = true
        panel.allowsMultipleSelection = false
        if panel.runModal() == .OK {
            documentsPermission = true
        }
        #else
        // iOS: document picker / sandbox access would go here.
        documentsPermission = true
        #endif
    }

    /// #2718 — When the person chose a provider, finishing hands off to the
    /// existing local-first Add Provider flow (full provider catalog +
    /// default-model selection) rather than hardcoding any single provider.
    /// Setting `isFirstLaunchProviderSetup` makes that sheet pre-select a local
    /// provider.
    private func finish() {
        if !isSetUp {
            featureManager.firstRunCompleted = true
            UserDefaults.standard.set(true, forKey: "hasCompletedOnboarding")
        }
        if wantsProviderSetup {
            appState.isFirstLaunchProviderSetup = true
            appState.showAddProvider = true
        }
        dismiss()
    }
}
