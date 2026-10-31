import FicheroAPIClient
import SwiftUI

/// Step 4, "Ready" (#5492): the plan as one list, what runs by itself (one choice), the optional
/// rows Check on your pages and Keep an export, then Start (the window's button). The plan is
/// proposed on arrival and kept as a draft whenever it changes, so Start's estimate is the
/// engine's plan for exactly what is shown.
struct RecipeReadyFields: View {
    @Bindable var store: RecipeSetupStore
    let onFix: (String) -> Void
    /// The project's comparison of readers (Check on your pages); nil without a project.
    var bakeoff: BakeoffSection.Context?
    /// The project's kept exports (Keep an export); nil without a project.
    var keptExports: KeptExportStore?
    /// The project whose model finder opens beside a reading step (#5611); nil without a project.
    var project: LibraryManager.LibraryReference?
    /// Start, pressed in the last box beside the total and why it waits (#5840).
    var onStart: () -> Void = {}
    var isStarting = false

    var body: some View {
        // Native grouped sections, as System Settings draws them (#5840): a box per step, then the parts.
        Form {
            if let error = store.errorMessage {
                Section {
                    Label(error, systemImage: "exclamationmark.triangle").foregroundStyle(.orange)
                    // A Start refused while the plan is over a cap offers its fixes here, where the error is (#6295): the plan's
                    // `cloud_cap.over` decides, not the words of the error.
                    if let cap = store.startPlan?.cloudCap, CloudCapFix.isOver(cap) {
                        CloudCapOffers(store: store, line: cap, undo: project?.actionsService)
                    }
                }
            }
            if store.isAssembling {
                Section { ProgressView() }
            } else if store.recipe == nil, !store.canAssemble {
                Section {
                    Text("Add at least one language and one script under Your Material.")
                        .font(.callout).foregroundStyle(.secondary)
                }
            }
            ForEach(sections, id: \.title) { section in
                Section {
                    sectionContent(section)
                } header: {
                    HStack(spacing: 6) {
                        Text(section.title)
                        if section.isOptional { Text("Optional").font(.caption).foregroundStyle(.secondary) }
                    }
                }
            }
        }
        .formStyle(.grouped)
        .task {
            await store.loadJobs()
            await store.loadPurposes()
            await store.assemble()
        }
        // The plan changed (proposed, a job added, the cloud answered): keep it, then ask what
        // Start would run, so the estimate and the Start button follow what is shown.
        .task(id: store.recipe) {
            guard store.recipe != nil, await store.save() else { return }
            await store.loadStartPlan()
        }
    }

    /// The boxes in order: the plan's steps numbered in run order, then the parts (`ReadySection`).
    private var sections: [ReadySection] {
        ReadySection.order(steps: (store.recipe?.steps ?? []).map { (id: $0.id, title: store.title(of: $0)) },
                           offersTraining: !store.trainOffers.isEmpty)
    }

    @ViewBuilder
    private func sectionContent(_ section: ReadySection) -> some View {
        switch section {
        case .step(_, let stepId, _):
            if let recipe = store.recipe {
                RecipeStepsView(store: store, recipe: recipe, onFix: onFix, finder: project, onlyStepId: stepId)
                if let step = recipe.steps.first(where: { $0.id == stepId }) {
                    RecipeStepRunLine(store: store, step: step)
                }
            }
        case .runsByItself:
            RecipeAutomaticFields(store: store)
        case .trainOffer:
            RecipeTrainOffersFields(store: store)
        case .start:
            if let recipe = store.recipe {
                RecipeTakenOutRows(store: store, removed: recipe.removed ?? [])
                RecipeCloudQuestion(store: store)
                RecipeMoneyAndPlaceFields(store: store)
            }
            RecipeStartFields(store: store, onFix: onFix, project: project)
            OfferedJobsList(store: store)
            StepChoiceMenusView(store: store)
            startRow
        case .checkOnYourPages:
            if let bakeoff {
                BakeoffSection(context: bakeoff, setup: store)
            } else {
                Text("Compare readers on your corrected pages, once the project has some.")
                    .font(.callout).foregroundStyle(.secondary)
            }
        case .keepAnExport:
            if let keptExports {
                KeptExportFields(store: keptExports)
            } else {
                Text("Keep an up-to-date copy of the work in a folder outside the project.")
                    .font(.callout).foregroundStyle(.secondary)
            }
        }
    }

    /// Start, with why it cannot start, and the last run's missed pages offered beside it.
    private var startRow: some View {
        HStack(alignment: .firstTextBaseline) {
            if let why = store.startDisabledReason {
                Label(why, systemImage: "info.circle").font(.callout).foregroundStyle(.secondary)
            }
            Spacer()
            if isStarting { ProgressView().controlSize(.small) }
            // What the project's last run missed, run again (#6170): the engine's offer, the strip's own Start on its folder;
            // a refusal shows above, in the store's error.
            if let project, let missed = Self.missed(in: project.activityStore), let offer = missed.offer {
                Button(offer) {
                    Task {
                        _ = await LibraryManager.shared.runAgainOnMissed(
                            for: project.id, folderId: missed.folderId, documents: missed.documents)
                    }
                }
                .help(missed.words)
                .disabled(isStarting)
                .accessibilityIdentifier("setup.ready.runAgainOnMissed")
            }
            Button("Start", action: onStart)
                .buttonStyle(.borderedProminent)
                .disabled(!store.canStart || isStarting)
                .keyboardShortcut(.defaultAction)
                .accessibilityIdentifier("setup.ready.start")
        }
    }

    /// What the project's last ended run missed, with its offer, as its run strip has it (`source.recipe.run-again-on-what-was-missed`).
    static func missed(in activity: ActivityStore?) -> ActivityDetails.MissedOffer? {
        activity.flatMap { ProjectRunStrip(store: $0) }?.missed.flatMap { $0.offer == nil ? nil : $0 }
    }

    /// Start (the first yes): the export rows are kept, the answers and plan saved, then the engine
    /// records the start. Each refusal stops there, with the engine's words on screen, and nothing
    /// starts. Returns whether the engine started.
    static func start(store: RecipeSetupStore, keptExports: KeptExportStore?) async -> Bool {
        if let keptExports, !(await keptExports.keepDrafts()) { return false }
        guard await store.save() else { return false }
        return await store.start(firstPages: store.runFirstPages)
    }
}

#Preview("Ready, nothing planned yet") {
    ScrollView {
        RecipeReadyFields(store: RecipeSetupStore(client: FicheroClient(libraryPath: nil)), onFix: { _ in })
            .padding()
    }
    .frame(width: 480, height: 520)
}
