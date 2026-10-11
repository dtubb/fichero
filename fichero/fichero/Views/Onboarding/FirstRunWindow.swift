#if canImport(AppKit)
import AppKit
#endif
import SwiftUI

/// Setting up, in one window and one code path (section 7d, ruled 2026-10-11, #5668): the app's pages (Welcome, What
/// Fichero runs, the hand-off), then Set Up a Project's (Your project, Add material, About the material, Choose the
/// Stages, one page per chosen stage, Train, Ready). A first launch shows the app's pages and, when the person sets up
/// a project, the project's after them; File › Set Up New Project… begins at Your project; Project › Set Up… begins
/// at Add material on the project it was asked for (`source.onboard.project.one-view`). Every page after Your
/// project reads and saves through THAT project's own store (`LibraryReference.recipeSetupStore`), so the engine
/// always knows which project (#5477).
struct FirstRunWindow: View {
    enum Mode {
        case firstRun
        case newProject
        case setUp
    }

    @Environment(AppState.self) var appState
    @Environment(\.dismiss) private var dismiss
    @Environment(\.openWindow) private var openWindow
    private let featureManager = FeatureManager.shared
    @State private var libraryManager = LibraryManager.shared

    @State private var step: SetupStep
    @State private var flow: SetupFlow
    /// Choose a Provider opens its sheet here, while What Fichero runs shows (`source.onboard.app.provider-sheet-in-step`);
    /// it used to open only once onboarding had finished.
    @State var showsProviderSheet = false
    /// The project setup works on: given for Set Up…, made by Your project otherwise.
    @State var project: LibraryManager.LibraryReference?
    @State var newProject = NewProjectStore(libraryManager: LibraryManager.shared)
    @State private var isSaving = false

    private let mode: Mode
    /// Tells the window which project setup made, when setup finishes, so it shows that project.
    private let onProjectReady: (UUID) -> Void

    /// `initialStep` and `newProject`: the onboarding screenshots' seam (`OnboardingScreenshotsTests`); the app passes neither.
    init(mode: Mode = .firstRun, project: LibraryManager.LibraryReference? = nil, initialStep: SetupStep? = nil,
         newProject: NewProjectStore? = nil, onProjectReady: @escaping (UUID) -> Void = { _ in }) {
        let flow = Self.flow(for: mode)
        self.mode = mode
        self.onProjectReady = onProjectReady
        _flow = State(initialValue: flow)
        _project = State(initialValue: project)
        _step = State(initialValue: initialStep ?? flow.steps.first ?? .welcome)
        if let newProject { _newProject = State(initialValue: newProject) }
    }

    /// The pages each way in starts with (`source.onboard.project.one-view`). Pure, for the tests.
    static func flow(for mode: Mode, isCompanionPlatform: Bool = SetupFlow.runsOnCompanionPlatform) -> SetupFlow {
        switch mode {
        case .firstRun: SetupFlow(includesApp: true, project: .none, isCompanionPlatform: isCompanionPlatform)
        case .newProject: SetupFlow(includesApp: false, project: .new)
        case .setUp: SetupFlow(includesApp: false, project: .existing)
        }
    }

    /// The store of the project being set up; nil until Your project has made one.
    var store: RecipeSetupStore? { project?.recipeSetupStore }

    /// The pages, with one per stage chosen so far.
    private var steps: [SetupStep] {
        var current = flow
        current.chosenStages = store?.chosenStageIds ?? []
        return current.steps
    }

    var body: some View {
        HStack(spacing: 0) {
            sidebar
            Divider()
            // minWidth 0: a wide row never pushes the sheet past its window (#5624).
            content
                .frame(minWidth: 0, maxWidth: .infinity, maxHeight: .infinity)
                .clipped()
        }
        // The fixed two-pane card is a desktop window size; a compact companion
        // presentation sizes to its sheet instead (#2807).
        #if os(macOS)
        .frame(width: 820, height: 600)
        #endif
        // Reopen where the person left off: the project's saved answers and
        // recipe (GET /api/recipes/project), the purposes, the jobs and the stages.
        .task(id: project?.id) {
            guard let store else { return }
            await store.loadSaved()
            await store.loadPurposes()
            await store.loadJobs()
            await store.loadStages()
        }
        .sheet(isPresented: $showsProviderSheet) {
            AddProviderSheet(onAdd: { await appState.loadProviders() }, isFirstLaunch: true)
                .environment(appState.providerService)
        }
    }

    /// The person chose to set up a project from the app's pages: the project's pages follow them.
    func setUpAProject() {
        flow.project = .new
        step = step.next(in: steps)
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
                if await RecipeReadyFields.start(store: store, keptExports: project?.keptExportStore) {
                    showStartedRun(store)
                    finish()
                }
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

            let titles = store?.stageTitles ?? [:]
            List(steps, selection: Binding(get: { step }, set: { if let chosen = $0 { step = chosen } })) { item in
                Label(item.title(stageTitles: titles), systemImage: item.icon)
                    .tag(item)
                    // Nothing after Your project can be reached before there is a project.
                    .disabled(store == nil && !item.needsNoProject)
            }
            .listStyle(.sidebar)
            .scrollContentBackground(.hidden)
        }
        .padding(20)
        .frame(width: 230)
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
                subtitle: FirstLaunchChoices.welcome,
                systemImage: "doc.richtext",
                showsContinue: false
            ) {
                // Less is more (Daniel, 2026-10-11): the welcome is its sentence and its two choices; the
                // steps are in the list beside it, so no card restates them, and no feature pills. Either choice
                // goes on to What Fichero runs; the hand-off then leads into the project, or into the app.
                VStack(spacing: 12) {
                    Spacer()
                    Button(action: {
                        flow.project = .new
                        advance()
                    }, label: {
                        Label(FirstLaunchChoices.setUpNewProject, systemImage: "arrow.right")
                            .frame(maxWidth: .infinity)
                    })
                    .buttonStyle(.borderedProminent)
                    .controlSize(.large)
                    Button(FirstLaunchChoices.startWithoutProject) { advance() }
                        .buttonStyle(.bordered)
                }
            }
        case .whatFicheroRuns:
            stepPage(
                title: WhatFicheroRuns.title,
                subtitle: WhatFicheroRuns.subtitle,
                systemImage: SetupStep.whatFicheroRuns.icon
            ) {
                WhatFicheroRunsFields(providers: appState.providerService,
                                      chooseProvider: { showsProviderSheet = true },
                                      onAccountAdded: { await appState.loadProviders() })
            }
        case .handOff:
            stepPage(
                title: flow.project == .none ? "Fichero is ready" : "Next, your project",
                subtitle: flow.project == .none
                    ? "Set up a project when you have material, or start in the one Fichero always has."
                    : "Name it, add your material, and choose what Fichero does with it.",
                systemImage: SetupStep.handOff.icon
            ) {
                if flow.project == .none {
                    Button(FirstLaunchChoices.setUpNewProject) { setUpAProject() }
                        .buttonStyle(.bordered)
                }
            }
        default:
            recipeStepPage(step)
        }
    }

    func stepPage<Content: View>(
        title: String,
        subtitle: String,
        systemImage: String,
        showsContinue: Bool = true,
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

            body().frame(minWidth: 0, maxWidth: .infinity, alignment: .leading)  // keeps the buttons on (#5624)

            Spacer(minLength: 0)
            HStack {
                Button(mode == .setUp ? "Close" : "Skip") { finish() }
                    .buttonStyle(.plain)
                    .foregroundStyle(.secondary)
                Spacer()
                if isSaving || newProject.isCreating { ProgressView().controlSize(.small) }
                Button("Back") { step = step.previous(in: steps) }
                    .disabled(step == steps.first)
                // One Continue per step, the footer's (`source.onboard.app.one-continue`); the welcome's choices
                // are its own buttons.
                if showsContinue {
                    Button(step == .ready ? "Start" : step == steps.last ? "Finish" : "Continue") {
                        advance()
                    }
                    .disabled(step == .ready && !(store?.canStart ?? false))
                    .help(step == .ready ? (store?.startDisabledReason ?? "") : "")
                    .buttonStyle(.borderedProminent)
                    .keyboardShortcut(.defaultAction)
                }
            }
        }
        .padding(28)
    }

    /// Start closes setup onto the run it queued (#5576, `source.onboard.auto.lands-on-the-run`):
    /// the Activity details of the recipe run, the one view of a run, its stages, pages done and
    /// left, time left and what it waits for; and, when it ends, what it made (#5577).
    private func showStartedRun(_ store: RecipeSetupStore) {
        #if os(macOS)
        guard let selection = Self.startedRunSelection(jobId: store.startedRunJobId, projectId: project?.id) else { return }
        ActivityWindowSelectionState.shared.select(selection)
        openWindow(id: ActivityWindowSelectionState.detailWindowID)
        #endif
    }

    /// The Activity row Start lands on: the recipe run in its project; nil before the engine kept Start.
    static func startedRunSelection(jobId: String?, projectId: UUID?) -> ActivitySelection? {
        guard let jobId, let projectId else { return nil }
        return ActivitySelection(jobId: jobId, libraryId: projectId)
    }

    /// Finishing marks first run done and shows a project setup made in the window. The provider sheet is no longer
    /// deferred to here: it opens in What Fichero runs.
    private func finish() {
        if mode == .firstRun {
            featureManager.firstRunCompleted = true
            UserDefaults.standard.set(true, forKey: "hasCompletedOnboarding")
        }
        if mode != .setUp, let made = newProject.created {
            onProjectReady(made.id)
        }
        dismiss()
    }
}
