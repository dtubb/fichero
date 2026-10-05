import FicheroAPIClient
import SwiftUI

// Setup's later screens (section 7b): each ticked job's own screen, How it will be done, What
// runs by itself and Start. No disclosure anywhere (#5481): what a step needs to say is said once.

/// A ticked job's own screen (`source.onboard.job-detail-screens`, ruled 2026-10-05): what the
/// job does, in the registry's words (its paragraph and its example), and the questions the
/// engine cannot work out by itself, for the jobs that have them.
struct SetupJobFields: View {
    @Bindable var store: RecipeSetupStore
    let job: String

    static let entityKinds: [(id: String, title: String)] = [
        ("people", "People"), ("places", "Places"), ("organisations", "Organisations"),
        ("dates", "Dates"), ("things", "Things (objects, goods)"), ("events", "Events")
    ]

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            if let topic = store.explanation(ofJob: job) {
                Text(topic.long).fixedSize(horizontal: false, vertical: true)
                if let example = topic.example {
                    Label(example, systemImage: "doc.text.magnifyingglass")
                        .font(.callout)
                        .foregroundStyle(.secondary)
                }
            } else if let described = store.jobs[job]?.description {
                Text(described)
            }
            questions
        }
        .textSelection(.enabled)
    }

    @ViewBuilder
    private var questions: some View {
        switch job {
        case "find-names-tag-words":
            Divider()
            Text("What to find").font(.headline)
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
            }
        case "translate-transliterate-normalise":
            Divider()
            Picker("How far", selection: $store.jobAnswers.normaliseHowFar) {
                Text("As written").tag("as-written")
                Text("Abbreviations expanded").tag("expanded")
                Text("Normalised spelling").tag("normalised")
            }
            .setupRadioGroup()
        case "place-in-a-gazetteer":
            Divider()
            Picker("Gazetteer", selection: $store.jobAnswers.gazetteer) {
                Text("GeoNames").tag("geonames")
                Text("Wikidata").tag("wikidata")
                Text("The project's own list").tag("project")
            }
            .setupRadioGroup()
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

/// Screen 6, "How it will be done" (#5481): the recipe the engine's rules propose, one row per
/// step with one sentence; a step's problem once, with its fix as a button; the one cloud
/// question; and every other job, which the person can add.
struct RecipeProposalFields: View {
    @Bindable var store: RecipeSetupStore
    /// A step problem's fix was pressed (its `fix`: download, choose-cloud, choose-model, …).
    let onFix: (String) -> Void
    /// Check on your pages under the reading step (#4951); nil before there is a project.
    var bakeoff: BakeoffSection.Context?

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            if let error = store.errorMessage {
                Label(error, systemImage: "exclamationmark.triangle").foregroundStyle(.orange)
            }
            if store.isAssembling {
                ProgressView()
            } else if let recipe = store.recipe {
                RecipeStepsView(store: store, recipe: recipe, onFix: onFix, bakeoff: bakeoff)
                RecipeCloudQuestion(store: store)
            } else if !store.canAssemble {
                Text("Add at least one language and one script under What It Is.")
                    .font(.callout).foregroundStyle(.secondary)
            }
            OfferedJobsList(store: store)
        }
        .task {
            await store.loadJobs()
            await store.assemble()
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

/// Screen 7, "What runs by itself" (#5478, `source.onboard.what-runs-by-itself`): Nothing runs
/// automatically, or new material runs through the ticked steps, pre-ticked by the purposes.
struct RecipeAutomaticFields: View {
    @Bindable var store: RecipeSetupStore

    var body: some View {
        let answer = store.automaticAnswer
        VStack(alignment: .leading, spacing: 10) {
            Picker("After Start", selection: Binding(
                get: { answer.runs },
                set: { store.automatic = .init(runs: $0, steps: answer.steps) }
            )) {
                Text("Nothing runs automatically").tag(false)
                Text("New material runs through the ticked steps").tag(true)
            }
            .setupRadioGroup()
            .labelsHidden()
            ForEach(store.recipe?.steps ?? [], id: \.id) { step in
                Toggle(store.title(of: step), isOn: Binding(
                    get: { answer.steps.contains(step.job) },
                    set: { on in
                        let steps = on ? answer.steps + [step.job] : answer.steps.filter { $0 != step.job }
                        store.automatic = .init(runs: answer.runs, steps: steps)
                    }
                ))
                .setupCheckbox()
                .disabled(!answer.runs)
                .padding(.leading, 20)
            }
            Text("Start runs the recipe once over the material already in the project. After Start, each "
                 + "import runs only the ticked steps over the pages it brought; with Nothing runs "
                 + "automatically, an import runs nothing. An unticked step runs only when you run it.")
                .font(.callout)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .task { await store.loadPurposes() }
    }
}

/// The Start step: what the recipe will run, on how many pages, what it costs, and any step
/// the engine refuses, by name (`source.project.automatic-after-first-yes`,
/// `source.onboard.estimate-before-start`). The engine plans; this only shows the plan.
struct RecipeStartFields: View {
    let store: RecipeSetupStore

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            if let plan = store.startPlan {
                Text("\(plan.estimate.pages) pages · \(Self.cost(plan.estimate.totalCostUsd))")
                    .font(.headline)
                ForEach(Array(plan.workflows.enumerated()), id: \.offset) { _, run in
                    Label("\(run.workflow) — \(run.steps.joined(separator: ", "))",
                          systemImage: run.runsOn.hasPrefix("cloud") ? "cloud" : "desktopcomputer")
                        .font(.body)
                }
                if !plan.offered.isEmpty {
                    Text("Offered later: \(plan.offered.joined(separator: ", "))")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                ForEach(plan.refusals, id: \.self) { refusal in
                    Label(refusal, systemImage: "exclamationmark.triangle")
                        .font(.caption)
                        .foregroundStyle(.orange)
                }
            } else if store.errorMessage == nil {
                ProgressView("Planning what Start would run…")
            }
            if let message = store.errorMessage {
                Text(message).font(.caption).foregroundStyle(.red)
            }
        }
        .task { await store.loadStartPlan() }
    }

    /// Unpriced is not free: a missing total is shown as unknown, never $0.
    static func cost(_ value: Double?) -> String {
        guard let value else { return "price unknown" }
        return value == 0 ? "free, runs on this Mac" : value.formatted(.currency(code: "USD"))
    }
}

#Preview("A job's screen") {
    SetupJobFields(store: RecipeSetupStore(client: FicheroClient(libraryPath: nil)), job: "find-names-tag-words")
        .padding()
        .frame(width: 520, height: 360)
}

#Preview("How it will be done") {
    let store = RecipeSetupStore(client: FicheroClient(libraryPath: nil))
    store.languages = ["es"]
    store.scripts = ["Latn"]
    return ScrollView { RecipeProposalFields(store: store, onFix: { _ in }).padding() }
        .frame(width: 520, height: 420)
}

#Preview("What runs by itself") {
    RecipeAutomaticFields(store: RecipeSetupStore(client: FicheroClient(libraryPath: nil)))
        .padding()
        .frame(width: 520, height: 300)
}

#Preview("Start") {
    RecipeStartFields(store: RecipeSetupStore(client: FicheroClient(libraryPath: nil)))
        .padding()
        .frame(width: 520, height: 300)
}
