import FicheroAPIClient
import SwiftUI

// Setup's questions under a ticked purpose (step 3) and its last step, Ready (step 4): section 7b,
// four steps ruled 2026-10-06 (#5492). No disclosure anywhere (#5481): what a step needs to say
// is said once.

/// The questions one job asks, opened in place under the ticked purpose that brings it (step 3;
/// the per-job screens of 2026-10-05 are gone, #5492): which kinds of names, which gazetteer, into
/// what form. Answers go to `answers.job_answers`; a job with no question shows nothing.
struct JobQuestionFields: View {
    @Bindable var store: RecipeSetupStore
    let job: String

    static let entityKinds: [(id: String, title: String)] = [
        ("people", "People"), ("places", "Places"), ("organisations", "Organisations"),
        ("dates", "Dates"), ("things", "Things (objects, goods)"), ("events", "Events")
    ]

    var body: some View {
        switch job {
        case "find-names-tag-words":
            VStack(alignment: .leading, spacing: 4) {
                Text("Which kinds of names").font(.headline)
                HStack(spacing: 14) {
                    ForEach(Self.entityKinds, id: \.id) { kind in
                        Toggle(kind.title, isOn: Binding(
                            get: { store.jobAnswers.entityKinds.contains(kind.id) },
                            set: { on in
                                if on {
                                    store.jobAnswers.entityKinds.append(kind.id)
                                } else {
                                    store.jobAnswers.entityKinds.removeAll { $0 == kind.id }
                                }
                            }
                        ))
                        .setupCheckbox()
                        .fixedSize()
                    }
                }
            }
        case "translate-transliterate-normalise":
            Picker("Into what", selection: $store.jobAnswers.normaliseHowFar) {
                Text("As written").tag("as-written")
                Text("Abbreviations expanded").tag("expanded")
                Text("Normalised spelling").tag("normalised")
            }
            .fixedSize()
        case "place-in-a-gazetteer":
            Picker("Which gazetteer", selection: $store.jobAnswers.gazetteer) {
                Text("GeoNames").tag("geonames")
                Text("Wikidata").tag("wikidata")
                Text("The project's own list").tag("project")
            }
            .fixedSize()
        default:
            EmptyView()
        }
    }
}

/// The one cloud question (`source.onboard.cloud-asked-once`), asked only when
/// the proposed recipe has a step a cloud model would also fit; otherwise it
/// says plainly that everything runs here. Changing it re-proposes the recipe.
struct RecipeCloudQuestion: View {
    @Bindable var store: RecipeSetupStore

    var body: some View {
        if store.asksCloudQuestion {
            VStack(alignment: .leading, spacing: 2) {
                Toggle("Pages may leave this Mac", isOn: $store.cloudAllowed)
                    .onChange(of: store.cloudAllowed) { Task { await store.assemble() } }
                Text("Asked once for this project. Off means nothing is sent to a cloud service.")
                    .font(.caption).foregroundStyle(.secondary)
            }
        } else {
            Label("Everything runs on this Mac.", systemImage: "desktopcomputer")
                .font(.callout)
                .foregroundStyle(.secondary)
        }
    }
}

/// The plan as one list (#5481): the recipe the engine's rules propose, one row per step with one
/// sentence; a step's problem once, with its fix as a button; the one cloud question; and every
/// other job, which the person can add.
struct RecipeProposalFields: View {
    @Bindable var store: RecipeSetupStore
    /// A step problem's fix was pressed (its `fix`: download, choose-cloud, choose-model, …).
    let onFix: (String) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            if let error = store.errorMessage {
                Label(error, systemImage: "exclamationmark.triangle").foregroundStyle(.orange)
            }
            if store.isAssembling {
                ProgressView()
            } else if let recipe = store.recipe {
                RecipeStepsView(store: store, recipe: recipe, onFix: onFix)
                RecipeCloudQuestion(store: store)
            } else if !store.canAssemble {
                Text("Add at least one language and one script under Your Material.")
                    .font(.callout).foregroundStyle(.secondary)
            }
            OfferedJobsList(store: store)
        }
    }
}

/// Every job the registry knows and the recipe does not have, each with Add: a purpose decides
/// what is offered first, never what can be reached (`source.onboard.offers-never-hides`).
struct OfferedJobsList: View {
    let store: RecipeSetupStore

    var body: some View {
        let inRecipe = Set((store.recipe?.steps ?? []).map(\.job))
        let others = store.offeredJobs.filter { !inRecipe.contains($0.id) }
        if !others.isEmpty {
            VStack(alignment: .leading, spacing: 6) {
                Divider()
                Text("Also on hand").font(.headline)
                ForEach(others, id: \.id) { job in
                    HStack(alignment: .firstTextBaseline) {
                        VStack(alignment: .leading, spacing: 1) {
                            Text(store.title(ofJob: job.id)).font(.callout)
                            if let topic = store.explanation(ofJob: job.id) {
                                Text(topic.short).font(.caption).foregroundStyle(.secondary)
                            }
                        }
                        Spacer()
                        Button("Add") {
                            store.toggle(job: job.id)
                            Task { await store.assemble() }
                        }
                        .controlSize(.small)
                    }
                }
            }
        }
    }
}

/// What runs by itself, as one choice (#5478, #5492, `source.onboard.what-runs-by-itself`):
/// Nothing runs automatically, or new material runs through the plan's steps.
struct RecipeAutomaticFields: View {
    @Bindable var store: RecipeSetupStore

    var body: some View {
        Picker("After Start", selection: Binding(
            get: { store.automaticAnswer.runs },
            set: { store.setRunsByItself($0) }
        )) {
            Text("Nothing runs automatically").tag(false)
            Text("New material runs through these steps").tag(true)
        }
        .setupRadioGroup()
        .help("Start runs the plan once over the material already in the project; this says what an import does after it.")
    }
}

/// What Start would cost and any step the engine refuses, by name
/// (`source.project.automatic-after-first-yes`, `source.onboard.estimate-before-start`). The
/// engine plans; this only shows the plan's estimate (its steps are the list above it).
struct RecipeStartFields: View {
    let store: RecipeSetupStore

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            if let plan = store.startPlan {
                Text("For the pages already here: \(plan.estimate.pages) pages · \(Self.cost(plan.estimate.totalCostUsd))")
                    .font(.headline)
                ForEach(plan.refusals, id: \.self) { refusal in
                    Label(refusal, systemImage: "exclamationmark.triangle")
                        .font(.callout)
                        .foregroundStyle(.orange)
                }
            } else if store.recipe != nil, store.errorMessage == nil {
                ProgressView("Planning what Start would run…").controlSize(.small)
            }
        }
    }

    /// Unpriced is not free: a missing total is shown as unknown, never $0.
    static func cost(_ value: Double?) -> String {
        guard let value else { return "price unknown" }
        return value == 0 ? "free, runs on this Mac" : value.formatted(.currency(code: "USD"))
    }
}

/// Step 4, "Ready" (#5492): the plan as one list, what runs by itself (one choice), the optional
/// rows Check on your pages and Keep an export, then Start (the window's button). The plan is
/// proposed on arrival and kept as a draft whenever it changes, so Start's estimate is the
/// engine's plan for exactly what is shown.
struct RecipeReadyFields: View {
    /// The rows of Ready, in order; the optional ones can be left and done later from the Inspector.
    enum Row: CaseIterable {
        case plan, runsByItself, checkOnYourPages, keepAnExport

        var title: String {
            switch self {
            case .plan: "The plan"
            case .runsByItself: "What runs by itself"
            case .checkOnYourPages: "Check on your pages"
            case .keepAnExport: "Keep an export"
            }
        }

        var isOptional: Bool { self == .checkOnYourPages || self == .keepAnExport }
    }

    @Bindable var store: RecipeSetupStore
    let onFix: (String) -> Void
    /// The project's comparison of readers (Check on your pages); nil without a project.
    var bakeoff: BakeoffSection.Context?
    /// The project's kept exports (Keep an export); nil without a project.
    var keptExports: KeptExportStore?

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            ForEach(Row.allCases, id: \.self) { row in
                if row != .plan { Divider() }
                Text(row.isOptional ? "\(row.title) (optional)" : row.title).font(.headline)
                content(row)
            }
        }
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

    @ViewBuilder
    private func content(_ row: Row) -> some View {
        switch row {
        case .plan:
            RecipeProposalFields(store: store, onFix: onFix)
            RecipeStartFields(store: store)
        case .runsByItself:
            RecipeAutomaticFields(store: store)
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

    /// Start (the first yes): the export rows are kept, the answers and plan saved, then the engine
    /// records the start. Each refusal stops there, with the engine's words on screen, and nothing
    /// starts. Returns whether the engine started.
    static func start(store: RecipeSetupStore, keptExports: KeptExportStore?) async -> Bool {
        if let keptExports, !(await keptExports.keepDrafts()) { return false }
        guard await store.save() else { return false }
        return await store.start()
    }
}

#Preview("Questions under a purpose") {
    VStack(alignment: .leading, spacing: 12) {
        JobQuestionFields(store: RecipeSetupStore(client: FicheroClient(libraryPath: nil)), job: "find-names-tag-words")
        JobQuestionFields(store: RecipeSetupStore(client: FicheroClient(libraryPath: nil)), job: "place-in-a-gazetteer")
    }
    .padding()
    .frame(width: 620, height: 160)
}

#Preview("Ready") {
    let store = RecipeSetupStore(client: FicheroClient(libraryPath: nil))
    store.languages = ["es"]
    store.scripts = ["Latn"]
    return ScrollView { RecipeReadyFields(store: store, onFix: { _ in }).padding() }
        .frame(width: 560, height: 520)
}

#Preview("What runs by itself") {
    RecipeAutomaticFields(store: RecipeSetupStore(client: FicheroClient(libraryPath: nil)))
        .padding()
        .frame(width: 520, height: 120)
}
