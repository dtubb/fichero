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

    /// The languages a reading can be translated into from Set Up (a tag the engine resolves): the scholarly ones a
    /// colonial archive is read into.
    static let translationLanguages: [(tag: String, name: String)] = [
        ("en", "English"), ("es", "Spanish"), ("fr", "French"), ("pt", "Portuguese"), ("de", "German"),
        ("it", "Italian"), ("la", "Latin")
    ]

    var body: some View {
        switch job {
        case "find-names-tag-words":
            VStack(alignment: .leading, spacing: 4) {
                Text("Which kinds of names").font(.headline)
                // Open-ended (#5805): every kind unless the person types some; chips from a sample try.
                StageKindsField(
                    question: store.stages.first { $0.id == "names" }?.questions.first { $0.key == "entity_kinds" }
                        ?? .init(key: "entity_kinds", ask: "Which kinds of names", kind: .many, readByAStep: true,
                                 openEnded: true),
                    answer: Binding(
                        get: { .many(store.jobAnswers.entityKinds) },
                        set: { if case .many(let kinds)? = $0 { store.jobAnswers.entityKinds = kinds } }
                    )
                )
            }
        case "translate-transliterate-normalise":
            // Several at once (#5660 item 1): each level ticked is its own run writing that reading.
            VStack(alignment: .leading, spacing: 4) {
                Text("Into what").font(.headline)
                FlowLayout(spacing: 12) {
                    ForEach(RecipeSetupAnswers.JobAnswers.normaliseLevels, id: \.id) { level in
                        Toggle(level.title, isOn: Binding(
                            get: { store.jobAnswers.writes(level: level.id) },
                            set: { store.jobAnswers.set(level: level.id, $0) }
                        ))
                        .setupCheckbox()
                        .fixedSize()
                    }
                }
                Picker("Also translate into", selection: Binding(
                    get: { store.jobAnswers.translation ?? "" },
                    set: { store.jobAnswers.translation = $0.isEmpty ? nil : $0 }
                )) {
                    Text("No translation").tag("")
                    ForEach(Self.translationLanguages, id: \.tag) { language in
                        Text(language.name).tag(language.tag)
                    }
                }
                .fixedSize()
            }
        case "place-in-a-gazetteer":
            Picker("Which place list", selection: $store.jobAnswers.gazetteer) {
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
                Toggle("Allow pages to be sent to a cloud service", isOn: $store.cloudAllowed)
                    .onChange(of: store.cloudAllowed) { Task { await store.assemble() } }
                Text("Cloud models often read difficult hands better and cost a few cents a page. Off: every page stays on this Mac. Change it any time in the Inspector.")
                    .font(.caption).foregroundStyle(.secondary)
            }
        } else {
            Label("Everything runs on this Mac.", systemImage: "desktopcomputer")
                .font(.callout)
                .foregroundStyle(.secondary)
        }
    }
}

/// The ruled money-and-place settings (#5769): the Hugging Face spend cap (shown with the cloud question, $0 offers
/// only) and, where a cluster is set up, whether working copies may stay on it. The engine says the values as they
/// stand and which clusters exist; the app only asks.
struct RecipeMoneyAndPlaceFields: View {
    @Bindable var store: RecipeSetupStore
    @FocusState private var capFocused: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            if store.cloudAllowed {
                HStack {
                    Text("Hugging Face spend a month, at most")
                    // The engine refuses a cap below $0 (the save fails), so the field never holds one.
                    TextField("0", value: Binding(get: { store.spendCapUsd },
                                                  set: { store.spendCapUsd = $0.map { max($0, 0) } }),
                              format: .currency(code: "USD"))
                        .multilineTextAlignment(.trailing).frame(maxWidth: 90)
                        .focused($capFocused)
                        .onSubmit { Task { _ = await store.save() } }
                        .onChange(of: capFocused) { _, focused in if !focused { Task { _ = await store.save() } } }
                }
                Text("$0 means paid offers stay offers: nothing paid starts without you. Spend shows against this on Start.")
                    .font(.caption).foregroundStyle(.secondary)
            }
            if let place = store.moneyAndPlace, !place.clusters.isEmpty {
                Toggle("Working copies may stay on \(place.clusters.formatted(.list(type: .or))) for re-runs",
                       isOn: Binding(get: { store.copiesMayStay ?? place.copiesMayStayOnCluster },
                                     set: { store.copiesMayStay = $0; Task { _ = await store.save() } }))
                if store.copiesMayStay == nil {
                    Text("Following your answer about pages leaving this Mac.").font(.caption).foregroundStyle(.secondary)
                }
            }
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
    /// The project whose model finder opens beside a reading step (#5611); nil without a project.
    var project: LibraryManager.LibraryReference?

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            if let error = store.errorMessage {
                Label(error, systemImage: "exclamationmark.triangle").foregroundStyle(.orange)
            }
            if store.isAssembling {
                ProgressView()
            } else if let recipe = store.recipe {
                RecipeStepsView(store: store, recipe: recipe, onFix: onFix, finder: project)
                RecipeTakenOutRows(store: store, removed: recipe.removed ?? [])
                RecipeCloudQuestion(store: store)
                RecipeMoneyAndPlaceFields(store: store)
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
                            Text(store.title(ofJob: job.id)).font(.body)
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
        VStack(alignment: .leading, spacing: 4) {
        Picker("After Start", selection: Binding(
            get: { store.automaticAnswer.runs },
            set: { store.setRunsByItself($0) }
        )) {
            Text("Nothing runs automatically").tag(false)
            Text("New material runs through these steps").tag(true)
        }
        .setupRadioGroup()
        Text("Start runs these steps once on what is here now. This decides what happens to pages you add later.")
            .font(.caption).foregroundStyle(.secondary)
        }
    }
}

/// What Start would cost, any step the engine refuses, by name, every step Start will skip with
/// why and its fix, and every model to fetch first with its size and Download
/// (`source.project.automatic-after-first-yes`, `source.onboard.estimate-before-start`,
/// `source.onboard.auto.plan-shows-what-will-not-run`, #5573). The engine plans; this only shows
/// the plan (its steps are the list above it).
struct RecipeStartFields: View {
    let store: RecipeSetupStore
    /// A skipped step's fix was pressed (its `fix`: choose-model, allow-cloud).
    var onFix: (String) -> Void = { _ in }
    /// The project whose downloads and model finder the rows use (#5619, #5620); nil without a project.
    var project: LibraryManager.LibraryReference?

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            if let plan = store.startPlan {
                Text("For the pages already here: \(plan.estimate.pages) pages · \(Self.cost(plan.estimate.totalCostUsd))")
                    .font(.headline)
                // In words, never the engine's raw message (section 7d, `source.onboard.ready.words-not-engine-errors`).
                ForEach(plan.refusals, id: \.self) { refusal in
                    Label(Self.words(for: refusal, title: store.title(ofJob:)), systemImage: "exclamationmark.triangle")
                        .font(.body)
                        .foregroundStyle(.orange)
                }
                // Steps that wait for a model already downloading (#5660): not a refusal, Start stays pressable.
                ForEach(store.waitingForDownloads, id: \.self) { waiting in
                    Label(waiting, systemImage: "arrow.down.circle")
                        .font(.body)
                        .foregroundStyle(.secondary)
                }
                RecipeDownloadRows(store: store)
                // Pages in iCloud, said before Start, with Copy into the Project (#5669).
                if let icloud = project?.icloudStore {
                    ICloudPagesNotice(store: icloud, actionsService: project?.actionsService)
                        .task(id: plan.inIcloud == nil) { icloud.adopt(fromPlan: store.startPlan) }
                }
                RecipeElsewhereRows(store: store)
                RecipeSkippedRows(store: store, onFix: onFix, project: project)
                RecipeBuiltInRows(store: store)
                // Steps left off until turned on, each with what it would cost and Turn On (#5677).
                RecipeLeftOffRows(store: store)
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
    /// The rows of Ready, in order; the optional ones can be left and done later from the Inspector. Training is its
    /// own page before Ready (section 7d, `source.onboard.stages.train-and-ready-last`), not a row here.
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
    /// The project whose model finder opens beside a reading step (#5611); nil without a project.
    var project: LibraryManager.LibraryReference?

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
            RecipeProposalFields(store: store, onFix: onFix, project: project)
            RecipeStartFields(store: store, onFix: onFix, project: project)
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

extension RecipeStartFields {
    /// A refusal as Ready says it (`source.onboard.ready.words-not-engine-errors`): the step by its title, not
    /// "step 1 (find-regions)", and a model the engine cannot run said as what to do, never its internal form.
    static func words(for refusal: String, title: (String) -> String) -> String {
        var text = refusal
        // "step 1 (find-regions): …" → "<Find regions' title>: …".
        if text.hasPrefix("step "), let open = text.firstIndex(of: "("), let close = text.range(of: "):"),
           open < close.lowerBound {
            let job = String(text[text.index(after: open)..<close.lowerBound])
            text = title(job) + ": " + text[close.upperBound...].trimmingCharacters(in: .whitespaces)
        }
        if text.contains("is not pinned in a known form") {
            let step = text.split(separator: ":").first.map(String.init) ?? "This step"
            text = "\(step): its model is not one Fichero can run yet. Choose a model for this step."
        }
        return text
    }
}
