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

/// The project's cloud switch (`source.onboard.cloud-asked-once`), always asked; under it, what each step a cloud
/// model would fit would send. Changing it re-proposes the recipe.
struct RecipeCloudQuestion: View {
    @Bindable var store: RecipeSetupStore

    var body: some View {
        // Always shown, so a project can turn cloud on before any step offers a cloud model.
        VStack(alignment: .leading, spacing: 2) {
            Toggle("Allow pages to be sent to a cloud service", isOn: $store.cloudChoice)
                .onChange(of: store.cloudAllowed) { Task { await store.assemble() } }
            Text("""
                Cloud models often read difficult hands better. Off: every page stays on this Mac. \
                Change it any time in the Inspector.
                """)
                .font(.caption).foregroundStyle(.secondary)
            // What would be sent, to whom, how many pages and the estimate: the engine's words, per step.
            ForEach(store.cloudOfferSentences, id: \.self) { sentence in
                Text(sentence).font(.caption).foregroundStyle(.secondary)
            }
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
                        .onSubmit { Task { if store.recipe != nil { _ = await store.save() } } }
                        .onChange(of: capFocused) { _, focused in if !focused, store.recipe != nil { Task { _ = await store.save() } } }
                }
                Text("$0 means paid offers stay offers: nothing paid starts without you. Spend shows against this on Start.")
                    .font(.caption).foregroundStyle(.secondary)
            }
            if let place = store.moneyAndPlace, !place.clusters.isEmpty {
                Toggle("Working copies may stay on \(place.clusters.formatted(.list(type: .or))) for re-runs",
                       isOn: Binding(get: { store.copiesMayStay ?? place.copiesMayStayOnCluster },
                                     set: { store.copiesMayStay = $0; Task { if store.recipe != nil { _ = await store.save() } } }))
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
                // The project's cloud cap beside the estimate, set here (`ai.where.cloud-spend-cap`).
                if let cap = plan.cloudCap { RecipeCloudCapRow(store: store, line: cap, undo: project?.actionsService) }
                // What Start changed in the saved recipe to fit kept choices (a page reader added the page step, a stale
                // choice dropped): said once, never a refusal (`source.recipe.page-reader-is-an-add-on`, #6259).
                ForEach(plan.notes ?? [], id: \.self) { note in
                    Label(note, systemImage: "info.circle").font(.callout).foregroundStyle(.secondary)
                }
                // In words, never the engine's raw message (section 7d, `source.onboard.ready.words-not-engine-errors`).
                // A refusal that names a step sits in that step's box (#5840), so only the others are here.
                let stepIds = Set((store.recipe?.steps ?? []).map(\.id))
                // The cap's refusal is said, with its fixes, by the cap row above (#6295): not twice.
                ForEach(plan.refusals.filter {
                    !CloudCapFix.isCapRefusal($0) && (Self.stepId(ofRefusal: $0).map { !stepIds.contains($0) } ?? true)
                }, id: \.self) { refusal in
                    Label(Self.words(for: refusal, title: store.title(ofJob:)), systemImage: "exclamationmark.triangle")
                        .font(.body)
                        .foregroundStyle(.orange)
                }
                // Steps that wait for a model already downloading (#5660): not a refusal, Start stays pressable. One that
                // names a step sits in that step's box (#5840); the others are here.
                ForEach(store.waitingForDownloads(notInSteps: Set((store.recipe?.steps ?? []).map(\.id))), id: \.self) { waiting in
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

/// Inside a step's box on Ready (#5840): the step's pages and cost from the Start plan, and the plan's refusals that name
/// this step, in words.
struct RecipeStepRunLine: View {
    let store: RecipeSetupStore
    let step: Components.Schemas.RecipeStep

    var body: some View {
        if let plan = store.startPlan {
            if let run = plan.estimate.runs.first(where: { $0.steps.contains(step.id) || $0.steps.contains(step.job) }) {
                Text("\(run.pages) pages · \(RecipeStartFields.cost(run.costUsd))")
                    .font(.callout).foregroundStyle(.secondary)
            }
            ForEach(plan.refusals.filter { RecipeStartFields.stepId(ofRefusal: $0) == step.id }, id: \.self) { refusal in
                Label(RecipeStartFields.words(for: refusal, title: store.title(ofJob:)), systemImage: "exclamationmark.triangle")
                    .font(.body).foregroundStyle(.orange)
            }
            ForEach(store.waitingForDownloads(inStep: step.id), id: \.self) { waiting in
                Label(waiting, systemImage: "arrow.down.circle").font(.body).foregroundStyle(.secondary)
            }
        }
    }
}

extension RecipeStartFields {
    /// The step a refusal names, by id ("step 1 (find-regions): …": the recipe's check writes the step's id there), or
    /// nil when it names none. Two steps of one job never share a refusal.
    static func stepId(ofRefusal refusal: String) -> String? {
        guard refusal.hasPrefix("step "), let open = refusal.firstIndex(of: "("),
              let close = refusal.range(of: "):"), open < close.lowerBound else { return nil }
        return String(refusal[refusal.index(after: open)..<close.lowerBound])
    }

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
