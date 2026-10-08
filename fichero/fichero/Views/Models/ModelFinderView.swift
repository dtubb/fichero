import FicheroAPIClient
import SwiftUI

/// The model finder (#5611, `source.find.app-finder-three-hosts`): one view, three hosts (the
/// project's Inspector, Set Up… › Ready beside a reading step's model, and Settings › AI). It shows
/// the engine's reader candidates for a query as cards (`source.find.app-card-says`), Search Online
/// with its "Searching online…" line followed through the project's Activity
/// (`source.find.app-searching-line`), and only the actions an existing route serves
/// (`source.find.app-card-actions`).
struct ModelFinderView: View {
    let store: ModelFinderStore
    let query: ModelFinderStore.Query
    /// The project's Activity, whose job list says how the online search is going; nil in previews.
    var activity: ActivityStore?
    /// Set Up…'s step, when the finder was opened beside one: Use for This Step is offered there.
    var step: Step?

    /// A step in Set Up… › Ready, with setup's own store (its recipe and `useCandidate`).
    struct Step {
        let id: String
        let setup: RecipeSetupStore
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            header
            ForEach(store.sources, id: \.source) { source in
                Text("\(ModelFinderStore.sourceWords(source.source.rawValue)): \(source.detail)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            if let failure = store.searchFailure {
                Label(failure, systemImage: "exclamationmark.triangle")
                    .font(.callout)
                    .foregroundStyle(.orange)
            }
            if let error = store.errorMessage {
                Label(error, systemImage: "exclamationmark.triangle")
                    .font(.callout)
                    .foregroundStyle(.orange)
            }
            if store.candidates.isEmpty, !store.isLoading, store.errorMessage == nil {
                Text("No reader was found for these answers yet. Search Online looks further.")
                    .font(.callout)
                    .foregroundStyle(.secondary)
            }
            ForEach(store.candidates, id: \.id) { candidate in
                ModelFinderCard(candidate: candidate, store: store, step: step)
            }
        }
        .task(id: query) { await store.load(query) }
        .onChange(of: activity?.backgroundJobs ?? []) { _, jobs in
            Task { await store.observe(jobs) }
        }
    }

    @ViewBuilder
    private var header: some View {
        HStack(alignment: .firstTextBaseline) {
            if let line = store.searchLine {
                ProgressView().controlSize(.small)
                Text(line).font(.callout).foregroundStyle(.secondary)
            } else if store.isLoading {
                ProgressView().controlSize(.small)
            }
            Spacer()
            // Pressing it again while a search runs is harmless: the engine reuses the running job.
            Button("Search Online") { Task { await store.searchOnline() } }
                .controlSize(.small)
                .disabled(query.scripts.isEmpty)
                .help("Look in Kraken's model repository and on Hugging Face; Activity shows the search")
        }
    }
}

/// One candidate as a card (`source.find.app-card-says`): its name, why it is offered, its size in
/// the engine's words, where it came from, what is measured here, a licence that is not open, and the
/// rules' refusal in place of an action.
struct ModelFinderCard: View {
    let candidate: Components.Schemas.ModelCandidate
    let store: ModelFinderStore
    var step: ModelFinderView.Step?

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            HStack(alignment: .firstTextBaseline) {
                Text(candidate.name).font(.headline)
                Spacer()
                actions
            }
            Text(candidate.offeredBecause).font(.callout)
            Text(Self.facts(candidate)).font(.caption).foregroundStyle(.secondary)
            Text(candidate.measured).font(.caption).foregroundStyle(.secondary)
            if let refused = candidate.refused {
                Label(refused, systemImage: "xmark.circle")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(8)
        .background(.quaternary.opacity(0.4), in: RoundedRectangle(cornerRadius: 8))
    }

    @ViewBuilder
    private var actions: some View {
        HStack(spacing: 6) {
            if store.downloading.contains(candidate.id) {
                Text("Downloading…").font(.callout).foregroundStyle(.secondary)
            } else if candidate.download != nil {
                Button("Download") { Task { await store.download(candidate) } }
                    .controlSize(.small)
                    .help("Download it to this Mac; Activity shows the download")
            }
            if let step {
                // Any candidate: the engine refuses, in words, one that does not do the step's job.
                Button("Use for This Step") {
                    Task { await step.setup.useCandidate(candidate, forStep: step.id) }
                }
                .controlSize(.small)
                .help("Read this step with it; a model still to download is then a download Start offers")
            }
        }
    }

    /// "Found on Hugging Face · 1.2 GB · Not on this Mac yet · Runs on this Mac · licence: cc-by-nc-4.0".
    static func facts(_ candidate: Components.Schemas.ModelCandidate) -> String {
        var parts = [ModelFinderStore.sourceWords(candidate.source.rawValue), candidate.size]
        if let installed = ModelFinderStore.installedWords(candidate.installed) {
            parts.append(installed)
        }
        parts.append(ModelFinderStore.placeWords(candidate.runsWhere.rawValue))
        if !candidate.openLicence, let licence = candidate.licence, !licence.isEmpty {
            parts.append("licence: \(licence)")
        }
        return parts.joined(separator: " · ")
    }
}

/// Find a Reader for a project, from its saved setup answers (the Inspector and Settings › AI): the
/// project's scripts, languages and first material. Says what to do when the project has none yet.
struct ProjectModelFinder: View {
    let library: LibraryManager.LibraryReference
    let setup: RecipeSetupStore

    var body: some View {
        if setup.scripts.isEmpty {
            Text("Set up the project's scripts and languages to find readers for them.")
                .font(.callout)
                .foregroundStyle(.secondary)
        } else {
            ModelFinderView(
                store: library.modelFinderStore,
                query: .init(scripts: setup.scripts, languages: setup.languages,
                             material: setup.materials.first ?? "handwriting"),
                activity: library.activityStore
            )
        }
    }
}

extension ModelFinderStore {
    /// Two candidates as the engine sends them, for previews: a shipped reader and a found one.
    static let previewList: Components.Schemas.ModelCandidateList? = {
        let json = """
        {"job":"read-a-line","count":2,"items":[
          {"id":"kraken:catmus@1","name":"CATMuS Medieval","source":"shipped",
           "offered_because":"a card that ships with Fichero","pin":{"zenodo":"10.5281/zenodo.1"},
           "jobs":["read-a-line"],"open_licence":true,"size":"0.02 GB","size_gb":0.02,
           "measured":"unmeasured on your pages until a bake-off measures it","in_recipe_rules":true,"rule_rank":1,
           "runs_where":"this_mac"},
          {"id":"mlx:hf/example/ocr-mlx@main","name":"Example OCR (MLX)","source":"hugging-face",
           "offered_because":"reads handwriting; lists Spanish; an MLX build this Mac runs",
           "pin":{"hf":"example/ocr-mlx","revision":"main"},"jobs":["read-a-line"],"licence":"cc-by-nc-4.0",
           "open_licence":false,"size":"size not stated",
           "measured":"unmeasured on your pages until a bake-off measures it","in_recipe_rules":true,"rule_rank":2,
           "installed":false,"runs_where":"this_mac",
           "download":{"runtime":"mlx","model":"example-ocr","action":"model.download",
                       "params":{"runtime":"mlx","model":"example-ocr"}}}],
         "sources":[{"source":"shipped","state":"read","count":1,"detail":"the cards that ship with Fichero"},
          {"source":"hugging-face","state":"cached","count":1,"detail":"the readers earlier searches found"}]}
        """
        return try? JSONDecoder().decode(Components.Schemas.ModelCandidateList.self, from: Data(json.utf8))
    }()
}

#Preview("Model finder") {
    ScrollView {
        ModelFinderView(
            store: ModelFinderStore(client: FicheroClient(libraryPath: nil), list: ModelFinderStore.previewList),
            query: .init(scripts: ["Latn"], languages: ["es"])
        )
        .padding()
    }
    .frame(width: 420, height: 420)
}

#Preview("Model finder card") {
    if let candidate = ModelFinderStore.previewList?.items.last {
        ModelFinderCard(candidate: candidate, store: ModelFinderStore(client: FicheroClient(libraryPath: nil)))
            .padding()
            .frame(width: 420)
    }
}

#Preview("Project model finder") {
    LibraryPreviewFixtures.environment(
        Form {
            ProjectModelFinder(
                library: LibraryPreviewFixtures.library,
                setup: RecipeSetupStore(client: FicheroClient(libraryPath: nil))
            )
        }
        .formStyle(.grouped)
    )
    .frame(width: 320, height: 200)
}
