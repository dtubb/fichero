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

    /// The step list's width: its longest page name fits whole.
    static let sidebarWidth: CGFloat = 260
    /// The window's size on the Mac; the content column gets what the step list leaves.
    static let windowSize = CGSize(width: 820, height: 600)

    @State private var step: SetupStep
    @State private var flow: SetupFlow
    /// Models & Services' Add… opens Settings' own add-provider sheet here, preselected or not
    /// (`source.onboard.app.provider-sheet-in-step`).
    @State var addProvider: AddProviderRequest?
    /// Where models may run, the engine's setting (#5828).
    @State private var placesStore: AppPlacesStore?
    @State private var clusterNames: [String] = []
    @State private var signingInToCluster = false
    /// The project setup works on: given for Set Up…, made by Your project otherwise.
    @State var project: LibraryManager.LibraryReference?
    @State var newProject = NewProjectStore(libraryManager: LibraryManager.shared)
    @State private var isSaving = false

    private let mode: Mode
    /// Tells the window which project setup made, when setup finishes, so it shows that project.
    private let onProjectReady: (UUID) -> Void

    /// `initialStep` and `newProject`: the onboarding screenshots' seam (`OnboardingScreenshotsTests`); the app passes neither.
    /// `setsUpAProject`: the previews' seam for the project's pages (a first launch itself never shows them).
    init(mode: Mode = .firstRun, project: LibraryManager.LibraryReference? = nil, initialStep: SetupStep? = nil,
         newProject: NewProjectStore? = nil, setsUpAProject: Bool = false,
         onProjectReady: @escaping (UUID) -> Void = { _ in }) {
        var flow = Self.flow(for: mode)
        if setsUpAProject, flow.project == .none { flow.project = .new }
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
        .frame(width: Self.windowSize.width, height: Self.windowSize.height)
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
        .sheet(item: $addProvider) { request in
            AddProviderSheet(onAdd: { await appState.loadProviders() }, preselectedType: request.providerType)
                .environment(appState.providerService)
        }
        .sheet(isPresented: $signingInToCluster, onDismiss: { Task { await loadClusterNames() } }) {
            AddClusterSheet(service: appState.hpcSignInService)
        }
        .task {
            if placesStore == nil { placesStore = AppPlacesStore(client: appState.ficheroClient) }
            await appState.loadProviders()
            await loadClusterNames()
        }
    }

    private func loadClusterNames() async {
        clusterNames = await appState.hpcSignInService.listClusters().map(\.name)
    }

    /// A card's button opens the existing screen for that job (one code path): a cloud key or a Hugging Face token
    /// through the add-provider sheet, ACENET through the cluster sign-in.
    private func connectPlace(_ connect: WhatFicheroRuns.Connect) {
        switch connect {
        case .addKey: addProvider = AddProviderRequest(providerType: nil)
        case .addToken: addProvider = AddProviderRequest(providerType: "huggingface")
        case .signIn: signingInToCluster = true
        }
    }

    /// Set Up a New Project… on Your First Project: this welcome closes, and the front window presents the new
    /// project's own Set Up in place (#5828; no new window).
    private func setUpNewProject() {
        libraryManager.newProjectSetUpAfterWelcome = true
        finish()
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
        // AI and ML Models: Continue writes the answer, the default included (`source.onboard.places-cap-projects`).
        if step == .whatFicheroRuns, let placesStore {
            Task {
                if await placesStore.keepAnswer() { step = step.next(in: steps) }
            }
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
            Text("Set Up Fichero")
                .font(.title2.weight(.semibold))
                .padding(.horizontal, 8)
                .padding(.bottom, 12)

            let titles = store?.stageTitles ?? [:]
            List(steps, selection: Binding(get: { step }, set: { if let chosen = $0 { step = chosen } })) { item in
                Label(item.title(stageTitles: titles), systemImage: item.icon)
                    .lineLimit(1)
                    .tag(item)
                    // Nothing after Your project can be reached before there is a project.
                    .disabled(store == nil && !item.needsNoProject)
            }
            .listStyle(.sidebar)
            .scrollContentBackground(.hidden)
        }
        // Wide enough that the longest page names ("About the Material", "Choose the Stages", "Structured Data")
        // never truncate in the sidebar list's own insets (Daniel's screenshot, 2026-10-11).
        .padding(.vertical, 20)
        .padding(.horizontal, 10)
        .frame(width: Self.sidebarWidth)
        .background(Color(platformColor: .controlBackgroundColor))
    }
}

// MARK: - Content & builders
extension FirstRunWindow {
    @ViewBuilder
    private var content: some View {
        switch step {
        case .welcome:
            // Less is more (Daniel, 2026-10-11): the welcome is the app's icon, its sentence and the space below;
            // its two choices are the footer's, as a Mac setup assistant's are.
            stepPage(title: "Welcome to Fichero", subtitle: "", systemImage: nil) {
                SetupBodyText(paragraphs: FirstLaunchChoices.welcomeParagraphs)
            }
        case .whatFicheroRuns:
            stepPage(title: WhatFicheroRuns.title, subtitle: "", systemImage: SetupStep.whatFicheroRuns.icon) {
                if let placesStore { WhatFicheroRunsFields(
                    store: placesStore,
                    setUp: WhatFicheroRuns.SetUp(providers: appState.providers, clusters: clusterNames),
                    connect: connectPlace) }
            }
        case .handOff:
            stepPage(title: "Your First Project", subtitle: "", systemImage: SetupStep.handOff.icon) {
                SetupBodyText(paragraphs: FirstLaunchChoices.handOffParagraphs)
            }
        default:
            recipeStepPage(step)
        }
    }

    /// One page: its icon (the app's on the welcome), title and subtitle, its content, and the footer.
    func stepPage<Content: View>(
        title: String,
        subtitle: String,
        systemImage: String?,
        @ViewBuilder body: () -> Content
    ) -> some View {
        VStack(alignment: .leading, spacing: 20) {
            HStack(spacing: 12) {
                pageIcon(systemImage)
                VStack(alignment: .leading, spacing: 3) {
                    Text(title)
                        .font(.title.weight(.semibold))
                    if !subtitle.isEmpty {
                        Text(subtitle)
                            .foregroundStyle(.secondary)
                    }
                }
            }

            body().frame(minWidth: 0, maxWidth: .infinity, alignment: .leading)  // keeps the buttons on (#5624)

            Spacer(minLength: 0)
            footer
        }
        .padding(28)
    }

    /// The page's symbol, or the app's icon at 64 pt where there is none (the welcome).
    @ViewBuilder
    private func pageIcon(_ systemImage: String?) -> some View {
        if let systemImage {
            Image(systemName: systemImage)
                .font(.title2)
                .foregroundStyle(Color.accentColor)
                .frame(width: 42, height: 42)
                .accessibilityHidden(true)
        } else {
            #if canImport(AppKit)
            Image(nsImage: NSApplication.shared.applicationIconImage)
                .resizable()
                .frame(width: 64, height: 64)
                .accessibilityHidden(true)
            #endif
        }
    }

    /// The Mac setup assistant's footer (`SetupFooter`): the one secondary choice at the far left, then Back and
    /// the default button at the far right. Regular push buttons, no icons.
    private var footer: some View {
        let model = SetupFooter.of(step, in: steps, mode: mode, projectChosen: flow.project != .none,
                                   hasMaterial: store?.hasMaterial ?? false)
        let waits = model.waitsFor ?? (step == .ready ? store?.startDisabledReason : nil)
        return HStack {
            if let leading = model.leading {
                Button(leading.title) { perform(leading.action) }
            }
            Spacer()
            // A greyed Start or Continue says why beside it, not only on hover (#5801, #5813). Ready's Start and its
            // reason are in the page's last box instead (#5840).
            if let reason = waits, !model.primaryLivesInPage {
                Text(reason).font(.callout).foregroundStyle(.secondary).lineLimit(2)
                    .accessibilityIdentifier("setup.footer.startReason")
            }
            if isSaving || newProject.isCreating { ProgressView().controlSize(.small) }
            if model.showsBack {
                Button("Back") { step = step.previous(in: steps) }
            }
            if !model.primaryLivesInPage {
                Button(model.primary.title) { perform(model.primary.action) }
                    .disabled(model.waitsFor != nil || (step == .ready && !(store?.canStart ?? false)))
                    .help(waits ?? "")
                    .keyboardShortcut(.defaultAction)
            }
        }
        .accessibilityIdentifier("setup.footer")
    }

    /// Ready's Start, pressed in the page's last box (#5840).
    func startFromReady() { advance() }

    /// What a footer button does.
    private func perform(_ action: SetupFooter.Action) {
        switch action {
        case .advance, .start:
            advance()
        case .setUpNewProject:
            setUpNewProject()
        case .skip:
            step = step.next(in: steps)
        case .finish, .close:
            finish()
        }
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
