#if canImport(AppKit)
import AppKit
#endif
import SwiftUI

/// First run, File › Set Up New Project… and Set Up… are one flow in four steps (section 7b,
/// ruled 2026-10-06, #5492; `source.onboard.screens-in-order`). First run and a new project
/// begin at Your project, which makes the project; Set Up… begins at Your material on the
/// project it was asked for. Every step after Your project reads and saves through THAT
/// project's own store (`LibraryReference.recipeSetupStore`), so the engine always knows which
/// project (#5477).
struct FirstRunWindow: View {
    enum Mode {
        case firstRun
        case newProject
        case setUp
    }

    @Environment(AppState.self) var appState
    @Environment(\.dismiss) private var dismiss
    private let featureManager = FeatureManager.shared
    @State private var libraryManager = LibraryManager.shared

    @State private var step: FirstRunStep
    @State private var documentsPermission = false
    /// "Choose a Provider" on the AI step no longer ends the flow (the recipe
    /// steps follow it); the Add Provider sheet opens when the flow finishes.
    @State private var wantsProviderSetup = false
    /// The project setup works on: given for Set Up…, made by Your project otherwise.
    @State var project: LibraryManager.LibraryReference?
    @State var newProject = NewProjectStore(libraryManager: LibraryManager.shared)
    @State private var isSaving = false

    private let steps: [FirstRunStep]
    private let mode: Mode
    /// Tells the window which project setup made, when setup finishes, so it shows that project.
    private let onProjectReady: (UUID) -> Void

    init(mode: Mode = .firstRun,
         project: LibraryManager.LibraryReference? = nil,
         onProjectReady: @escaping (UUID) -> Void = { _ in }) {
        let steps: [FirstRunStep] = switch mode {
        case .firstRun: FirstRunStep.steps(isCompanionPlatform: FirstRunStep.isCompanionPlatform)
        case .newProject: FirstRunStep.newProjectSteps
        case .setUp: FirstRunStep.setUpSteps
        }
        self.steps = steps
        self.mode = mode
        self.onProjectReady = onProjectReady
        _project = State(initialValue: project)
        _step = State(initialValue: steps.first ?? .welcome)
    }

    /// The store of the project being set up; nil until Your project has made one.
    var store: RecipeSetupStore? { project?.recipeSetupStore }

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
        .frame(width: 820, height: 600)
        #endif
        // Reopen where the person left off: the project's saved answers and
        // recipe (GET /api/recipes/project), and the purposes and jobs for their questions.
        .task(id: project?.id) {
            guard let store else { return }
            await store.loadSaved()
            await store.loadPurposes()
            await store.loadJobs()
        }
    }

    /// Advance within the steps; the LAST one finishes (#2807).
    private func advance() {
        // Your project makes the project; the steps after it save into it.
        if step == .project {
            Task {
                guard let made = await newProject.create() else { return }
                project = made
                step = step.next(in: steps)
            }
            return
        }
        // Ready's Start keeps the exports, saves, and records the first yes; the window closes
        // only when the engine kept it.
        if step == .ready, let store {
            Task {
                isSaving = true
                defer { isSaving = false }
                if await RecipeReadyFields.start(store: store, keptExports: project?.keptExportStore) { finish() }
            }
            return
        }
        if step == steps.last {
            finish()
            return
        }
        // Continue keeps the answers so far as a draft on the project, so setup can be closed
        // at any step; saving is not Start.
        guard step.savesDraft, let store else { step = step.next(in: steps); return }
        Task {
            isSaving = true
            let saved = await store.save()
            isSaving = false
            // A refused save stays on its step with the engine's words.
            if saved { step = step.next(in: steps) }
        }
    }

    private var sidebar: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Fichero")
                .font(.title2.weight(.semibold))
                .padding(.bottom, 12)

            List(steps, selection: Binding(get: { step }, set: { if let chosen = $0 { step = chosen } })) { item in
                Label(item.title, systemImage: item.icon)
                    .tag(item)
                    // Nothing after Your project can be reached before there is a project.
                    .disabled(store == nil && item != .project && !isBeforeProject(item))
            }
            .listStyle(.sidebar)
            .scrollContentBackground(.hidden)
        }
        .padding(20)
        .frame(width: 230)
        .background(Color(platformColor: .controlBackgroundColor))
    }

    private func isBeforeProject(_ item: FirstRunStep) -> Bool {
        [.welcome, .permissions, .cloud].contains(item)
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
                        title: "Set up your first project",
                        body: "Four steps: your project, your material, what you want to do, and the plan. "
                            + "Fichero proposes how the work will be done, and nothing runs until you press Start.",
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
        case .project, .material, .purpose, .ready:
            recipeStepPage(step)
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
                    .accessibilityHidden(true)
                VStack(alignment: .leading, spacing: 3) {
                    Text(title)
                        .font(.title.weight(.semibold))
                    Text(subtitle)
                        .foregroundStyle(.secondary)
                }
            }

            body()

            Spacer(minLength: 0)
            HStack {
                Button(mode == .setUp ? "Close" : "Skip") { finish() }
                    .buttonStyle(.plain)
                    .foregroundStyle(.secondary)
                Spacer()
                if isSaving || newProject.isCreating { ProgressView().controlSize(.small) }
                Button("Back") { step = step.previous(in: steps) }
                    .disabled(step == steps.first)
                Button(step == .ready ? "Start" : step == steps.last ? "Finish" : "Continue") {
                    advance()
                }
                .disabled(step == .ready && !(store?.canStart ?? false))
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
                .accessibilityHidden(true)

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
    /// provider. A project setup made is shown in the window.
    private func finish() {
        if mode == .firstRun {
            featureManager.firstRunCompleted = true
            UserDefaults.standard.set(true, forKey: "hasCompletedOnboarding")
        }
        if mode != .setUp, let made = newProject.created {
            onProjectReady(made.id)
        }
        if wantsProviderSetup {
            appState.isFirstLaunchProviderSetup = true
            appState.showAddProvider = true
        }
        dismiss()
    }
}
