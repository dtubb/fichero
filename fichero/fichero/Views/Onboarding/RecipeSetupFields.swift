import FicheroAPIClient
import SwiftUI
import UniformTypeIdentifiers

// The recipe screens of first run (`FirstRunStep.setUpSteps`, in the spec's order),
// as subviews `FirstRunWindow` hosts, so first run and the Inspector's Set Up…
// are one flow (`source.onboard.purpose-first`, `source.onboard.widget-and-search`,
// `source.onboard.five-questions`, `source.onboard.proposes-chain`). A form with
// search, not a conversation; the answers stay on the store; nothing runs here.

/// Step "Purpose": what the person is doing, in plain words, each purpose with
/// the engine's own description (`GET /api/recipes/purposes`).
struct RecipePurposeFields: View {
    @Bindable var store: RecipeSetupStore

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            if store.purposes.isEmpty, let error = store.errorMessage {
                Label(error, systemImage: "exclamationmark.triangle").foregroundStyle(.orange)
            } else if store.purposes.isEmpty {
                ProgressView()
            }
            Picker("Purpose", selection: $store.purpose) {
                ForEach(store.purposes, id: \.id) { purpose in
                    VStack(alignment: .leading, spacing: 2) {
                        Text(purpose.title)
                        Text(purpose.description)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    .tag(purpose.id)
                }
            }
            .pickerStyle(.inline)
            .labelsHidden()
            if let purpose = store.purposes.first(where: { $0.id == store.purpose }) {
                Text(purpose.runsByItself
                     ? "New material goes through these steps by itself."
                     : "Nothing runs by itself; this purpose's tools are offered first.")
                    .font(.caption).foregroundStyle(.secondary)
            }
        }
        .task { await store.loadPurposes() }
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
                let options = store.recipe?.cloudOptions ?? []
                Text(options.isEmpty
                     ? "Asked once for this project. Off means nothing is sent to a cloud service."
                     : "A cloud model would also fit: \(options.joined(separator: ", ")). "
                        + "Off means nothing is sent to a cloud service.")
                    .font(.caption).foregroundStyle(.secondary)
            }
        } else {
            Label("Everything runs on this Mac.", systemImage: "desktopcomputer")
                .font(.callout)
                .foregroundStyle(.secondary)
        }
    }
}

/// How sources come in (ruled 2026-10-03, `source.sync.four-ways-in`): Link,
/// Copy, Move or Index, each with what it does to the originals. Link is the
/// default; Move says plainly that the originals go.
struct ProjectIntakeChoice: View {
    @Bindable var store: RecipeSetupStore

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("How do your sources come in?").font(.headline)
            Picker("How do your sources come in?", selection: $store.ingestMode) {
                option("Link", "Fichero reads the files where they are and never changes the originals.")
                    .tag(IngestMode.link)
                option("Copy", "Fichero makes its own copy in the project; the originals are never touched.")
                    .tag(IngestMode.copy)
                option("Move", "The files move into the project, stored in the app; "
                       + "the originals are removed from where they were.")
                    .tag(IngestMode.move)
                option("Index", "Fichero works on the folder in place and writes its changes back "
                       + "into the original files, keeping that folder up to date. For folders; "
                       + "single files are linked.")
                    .tag(IngestMode.index)
            }
            .pickerStyle(.inline)
            .labelsHidden()
            if store.ingestMode == .move {
                Label("Your original files will be removed from where they are now.",
                      systemImage: "exclamationmark.triangle")
                    .font(.callout)
                    .foregroundStyle(.orange)
            }
        }
    }

    private func option(_ title: String, _ explanation: String) -> some View {
        VStack(alignment: .leading, spacing: 1) {
            Text(title)
            Text(explanation).font(.caption).foregroundStyle(.secondary)
        }
    }
}

/// Screen 2, "Your material": how sources come in, a folder to bring in now
/// (or later, from the project), and how much there is.
struct RecipeMaterialSourceFields: View {
    @Bindable var store: RecipeSetupStore
    /// The project's import path; nil where this window has no project open.
    let importer: ImportService?
    @State private var choosingFolder = false
    @State private var adding = false

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            ProjectIntakeChoice(store: store)
            Divider()
            HStack {
                Button("Add a Folder…") { choosingFolder = true }
                    .disabled(importer == nil || adding)
                if adding { ProgressView().controlSize(.small) }
            }
            Text(importer == nil
                 ? "Open a project to add material now, or add it later from the project."
                 : "Or add material later; it comes in the way chosen above.")
                .font(.caption).foregroundStyle(.secondary)
            if let added = store.materialAdded {
                Label(added, systemImage: "checkmark.circle").font(.callout)
            }
            if let error = store.errorMessage {
                Label(error, systemImage: "exclamationmark.triangle").foregroundStyle(.orange)
            }
            LabeledContent("Roughly how many pages") {
                TextField("Pages", value: $store.pages, format: .number).labelsHidden()
            }
        }
        .fileImporter(isPresented: $choosingFolder, allowedContentTypes: [.folder]) { result in
            guard case .success(let url) = result, let importer else { return }
            adding = true
            Task {
                await store.addFolder(url, importer: importer)
                adding = false
            }
        }
    }
}

/// Screen 3, "What it is": languages and scripts (each with search), what the
/// engine works out for each script, and the kind of material.
struct RecipeAboutFields: View {
    @Bindable var store: RecipeSetupStore

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            CodeSearchField(title: "Languages", prompt: "Name, BCP 47 tag or glottocode, e.g. es",
                            search: store.searchLanguages, codes: $store.languages)
            if let topic = store.topics.topic("languages") { TopicExplanation(topic: topic) }
            CodeSearchField(title: "Scripts", prompt: "Name or ISO 15924 code, e.g. Latn",
                            search: store.searchScripts, codes: $store.scripts)
            if let topic = store.topics.topic("scripts") { TopicExplanation(topic: topic) }
            ForEach(store.scripts, id: \.self) { code in
                if let facts = store.derivedScripts[code] {
                    DerivedScriptRow(facts: facts)
                }
            }
            Picker("Material", selection: $store.material) {
                ForEach(RecipeSetupStore.materials, id: \.self) { Text($0.capitalized).tag($0) }
            }
        }
        .task(id: store.scripts) { await store.loadDerived() }
        .task { await store.topics.load() }
    }
}

/// Screen 4, "How it will be done": the recipe the engine's rules propose from
/// the answers, each step explained in the topic registry's words, the one cloud
/// question, and every other tool, offered after the recipe's, never hidden.
struct RecipeProposalFields: View {
    @Bindable var store: RecipeSetupStore

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            if let error = store.errorMessage {
                Label(error, systemImage: "exclamationmark.triangle").foregroundStyle(.orange)
            }
            if store.isAssembling {
                ProgressView()
            } else if let recipe = store.recipe {
                RecipeStepsView(store: store, recipe: recipe)
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

/// Every job the registry knows, the recipe's first: a purpose decides what is
/// offered first, never what can be reached (`source.onboard.offers-never-hides`).
struct OfferedJobsList: View {
    let store: RecipeSetupStore

    var body: some View {
        let inRecipe = Set((store.recipe?.steps ?? []).map(\.job))
        let others = store.offeredJobs.filter { !inRecipe.contains($0.id) }
        if !others.isEmpty {
            DisclosureGroup("Also on hand (\(others.count))") {
                VStack(alignment: .leading, spacing: 6) {
                    ForEach(others, id: \.id) { job in
                        VStack(alignment: .leading, spacing: 1) {
                            Text(job.name).font(.callout)
                            if let topic = store.explanation(ofJob: job.id) {
                                Text(topic.short).font(.caption).foregroundStyle(.secondary)
                            }
                        }
                    }
                }
                .padding(.top, 4)
            }
        }
    }
}

/// What the engine worked out for one script, shown rather than asked
/// (`source.onboard.derives-not-asks`): direction, a bundled font, and, for a script that may be
/// written vertically, the one thing only the pages can settle.
private struct DerivedScriptRow: View {
    let facts: Components.Schemas.ScriptFacts

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text("\(facts.script): \(facts.direction == "rtl" ? "right to left" : "left to right")")
                .help(facts.directionFrom)
            if let font = facts.font {
                Text("Shown in \(font)").help(facts.fontFrom)
            }
            if facts.mayBeVertical {
                Label("May be written in vertical columns: check a page.", systemImage: "text.alignleft")
            }
        }
        .font(.caption)
        .foregroundStyle(.secondary)
    }
}

/// A field that adds codes by searching names or typing the code itself. Suggestions come from
/// the engine's catalogue (every ISO 639-3 language with Glottolog's, every ISO 15924 script); any
/// code typed is accepted as is, since the engine checks it.
struct CodeSearchField: View {
    let title: String
    let prompt: String
    let search: (String) async -> [RecipeSetupStore.CodeChoice]
    @Binding var codes: [String]
    @State private var query = ""
    @State private var matches: [RecipeSetupStore.CodeChoice] = []

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            LabeledContent(title) {
                TextField(title, text: $query, prompt: Text(prompt))
                    .labelsHidden()
                    .onSubmit { add(matches.first?.code ?? query.trimmingCharacters(in: .whitespaces)) }
            }
            ForEach(matches.filter { !codes.contains($0.code) }, id: \.self) { match in
                Button {
                    add(match.code)
                } label: {
                    VStack(alignment: .leading, spacing: 0) {
                        Text("\(match.name) (\(match.code))")
                        if let detail = match.detail { Text(detail).foregroundStyle(.secondary) }
                    }
                }
                .buttonStyle(.borderless)
                .font(.caption)
            }
            if !codes.isEmpty {
                HStack {
                    ForEach(codes, id: \.self) { code in
                        Button { codes.removeAll { $0 == code } } label: {
                            Label(code, systemImage: "xmark.circle.fill")
                        }
                        .buttonStyle(.bordered)
                        .controlSize(.small)
                    }
                }
            }
        }
        .task(id: query) {
            let needle = query.trimmingCharacters(in: .whitespaces)
            guard !needle.isEmpty else { matches = []; return }
            try? await Task.sleep(for: .milliseconds(200))  // typing: ask once the person pauses
            guard !Task.isCancelled else { return }
            matches = await search(needle)
        }
    }

    private func add(_ code: String) {
        guard !code.isEmpty, !codes.contains(code) else { return }
        codes.append(code)
        query = ""
        matches = []
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
            } else {
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

#Preview("Your material") {
    let store = RecipeSetupStore(client: FicheroClient(libraryPath: nil))
    store.ingestMode = .index
    store.pages = 1200
    return RecipeMaterialSourceFields(store: store, importer: nil)
        .padding()
        .frame(width: 520, height: 480)
}

#Preview("What it is") {
    let store = RecipeSetupStore(client: FicheroClient(libraryPath: nil))
    store.languages = ["es", "la"]
    store.scripts = ["Latn"]
    return RecipeAboutFields(store: store)
        .padding()
        .frame(width: 520, height: 320)
}

#Preview("How it will be done") {
    let store = RecipeSetupStore(client: FicheroClient(libraryPath: nil))
    store.languages = ["es"]
    store.scripts = ["Latn"]
    return ScrollView { RecipeProposalFields(store: store).padding() }
        .frame(width: 520, height: 420)
}

#Preview("Project intake") {
    ProjectIntakeChoice(store: RecipeSetupStore(client: FicheroClient(libraryPath: nil)))
        .padding()
}

#Preview("Start") {
    RecipeStartFields(store: RecipeSetupStore(client: FicheroClient(libraryPath: nil)))
        .padding()
        .frame(width: 520, height: 300)
}
