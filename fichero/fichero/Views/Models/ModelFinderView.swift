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
                Text(ModelFinderStore.sourceLine(source))
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            ForEach(store.htrUnited.datasets, id: \.key) { dataset in
                HtrUnitedDatasetRow(dataset: dataset)
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
                Text(Self.nothingFound(job: query.job))
                    .font(.callout)
                    .foregroundStyle(.secondary)
            }
            ForEach(ModelFinderTiers.groups(store.candidates), id: \.title) { group in
                if let title = group.title {
                    Text(title).font(.caption).foregroundStyle(.secondary).padding(.top, 4)
                }
                ForEach(group.candidates, id: \.id) { candidate in
                    ModelFinderCard(candidate: candidate, store: store, step: step)
                }
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

    /// What the finder says when the engine lists nothing for the step's job: a reader can be searched for
    /// online; any other job's model is one already on this Mac or on a server of yours (#5619).
    static func nothingFound(job: String) -> String {
        job == ModelFinderStore.readingJob || job == "read-a-page" || job == "find-where-readers-disagree"
            ? "No reader was found for these answers yet. Search Online looks further."
            : "No model on this Mac does this yet. A text model in your MLX store, or on an Ollama or LM Studio "
              + "server of yours (Settings › AI), is offered here once it is there."
    }
}

/// One candidate as a card (`source.find.app-card-says`): its name, why it is offered, its size in
/// the engine's words, where it came from, what is measured here, a licence that is not open, and the
/// rules' refusal in place of an action.
struct ModelFinderCard: View {
    let candidate: Components.Schemas.ModelCandidate
    let store: ModelFinderStore
    var step: ModelFinderView.Step?
    /// Opens Settings › AI for a card that asks for a provider first; absent in a preview.
    @Environment(AppState.self) private var appState: AppState?

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            HStack(alignment: .firstTextBaseline) {
                Text(candidate.shortName ?? candidate.name).font(.headline).help(candidate.name)
                Spacer()
                actions
            }
            if Self.isChosen(candidate) {
                Label("In use for this step", systemImage: "checkmark.circle.fill")
                    .font(.callout)
                    .foregroundStyle(.tint)
            }
            if let why = Self.whyOffered(candidate) {
                Text(why).font(.callout)
            }
            if Self.needsPermission(candidate) {
                Label(Self.permissionWords, systemImage: "lock")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                // Beside a Set Up step the answer is one press away: the same fix as the toggle's.
                if let step {
                    Button("Allow Cloud Models") { Task { await step.setup.allowCloud() } }
                        #if os(macOS)
                        .buttonStyle(.link)
                        #else
                        .buttonStyle(.borderless)
                        #endif
                        .font(.caption)
                }
            } else if Self.cannotRunHere(candidate) {
                // Why, once, in the engine's words ("Fichero cannot run it yet (…)"), with the one way on.
                Label(candidate.availabilityWords, systemImage: "xmark.circle")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                if Self.asksForSettings(candidate), let appState {
                    Button("Open Settings › AI") { appState.openSettings(tab: .aiModels) }
                        #if os(macOS)
                        .buttonStyle(.link)
                        #else
                        .buttonStyle(.borderless)
                        #endif
                        .font(.caption)
                }
            } else {
                Text(Self.facts(candidate)).font(.caption).foregroundStyle(.secondary)
            }
            Text(candidate.measured).font(.caption).foregroundStyle(.secondary)
            // Whether it fits this Mac, in the engine's words, with a smaller build as one press (#5641).
            if let fit = CandidateFit.of(candidate, in: store.candidates) {
                CandidateFitLabel(fit: fit, useSmaller: useSmaller)
            }
            // What its download's job says while it runs, or why it failed (#5620).
            if let key = ModelFinderStore.downloadKey(candidate), let line = store.downloads.line(key) {
                let failed = Self.failed(store.downloads.state(key))
                Label(line, systemImage: failed ? "exclamationmark.triangle" : "arrow.down.circle")
                    .font(.caption)
                    .foregroundStyle(failed ? .orange : .secondary)
                    .textSelection(.enabled)
            }
            if let refused = candidate.refused, !Self.cannotRunHere(candidate) {
                Label(refused, systemImage: "xmark.circle")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(8)
        .background(.quaternary.opacity(0.4), in: RoundedRectangle(cornerRadius: 8))
        // A model that won't fit is greyed out with its reason, never hidden (#5641).
        .foregroundStyle(Self.wontFit(candidate, in: store.candidates) || Self.needsPermission(candidate) ? .secondary : .primary)
    }

    /// Use <name> instead, beside a Set Up step only: the smaller build through the use-candidate route.
    private var useSmaller: ((CandidateFit.Smaller) -> Void)? {
        guard let step else { return nil }
        return { smaller in Task { await step.setup.useCard(smaller.card, named: smaller.name, forStep: step.id) } }
    }

    /// The engine says it won't fit this Mac: greyed, and not offered for the step.
    static func wontFit(_ candidate: Components.Schemas.ModelCandidate,
                        in list: [Components.Schemas.ModelCandidate]) -> Bool {
        CandidateFit.of(candidate, in: list)?.isGreyed == true
    }

    @ViewBuilder
    private var actions: some View {
        // A card Fichero cannot run yet has nothing to press: its why says what would change that.
        if !Self.cannotRunHere(candidate) { runnableActions }
    }

    @ViewBuilder
    private var runnableActions: some View {
        HStack(spacing: 6) {
            if let key = ModelFinderStore.downloadKey(candidate), Self.offersDownload(candidate) {
                if Self.isDownloading(candidate, tracked: store.downloads.isActive(key)) {
                    ProgressView().controlSize(.small)
                } else if store.downloads.state(key) != .done {
                    Button(Self.failed(store.downloads.state(key)) ? "Try Again" : "Download") {
                        Task { await store.download(candidate) }
                    }
                    .controlSize(.small)
                    .help("Download it to this Mac; Activity shows the download")
                }
            }
            if let step, !Self.isChosen(candidate), Self.offersUse(candidate),
               !Self.wontFit(candidate, in: store.candidates) {
                // The engine's `refused` says why a card cannot be used; its words show under the card.
                Button("Use for This Step") {
                    Task { await step.setup.useCandidate(candidate, forStep: step.id) }
                }
                .controlSize(.small)
                .help("Use it for this step; a model still to download is then a download Start offers")
            }
        }
    }

    /// A download is under way when this app is tracking it OR the engine says a `download-model` job is fetching it
    /// (`download.downloading`): a card the engine words "Downloading" never shows a Download button beside it (#5809).
    static func isDownloading(_ candidate: Components.Schemas.ModelCandidate, tracked: Bool) -> Bool {
        tracked || candidate.download?.downloading == true
    }

    static func failed(_ state: ModelDownloads.State?) -> Bool {
        if case .failed? = state { return true }
        return false
    }

    /// Where the card stands for this Mac, as the engine words it ("Available", "Download (2.3 GB)",
    /// "Runs at openai"), and a licence that is not open: "Download (16 MB) · licence: cc-by-nc-4.0" (#5660).
    static func facts(_ candidate: Components.Schemas.ModelCandidate) -> String {
        var parts = [candidate.availabilityWords]
        if !candidate.openLicence, let licence = candidate.licence, !licence.isEmpty {
            parts.append("licence: \(licence)")
        }
        return parts.joined(separator: " · ")
    }

    /// Fichero cannot run it yet (`availability` not_here: Apple Intelligence missing from this build, a cloud
    /// model with no provider set up): no Download, no Use for This Step (#5660 item 4).
    /// A cloud reader the person has not yet allowed (`needs_permission`, #5768): shown greyed, never pressed.
    static func needsPermission(_ candidate: Components.Schemas.ModelCandidate) -> Bool {
        candidate.needsPermission == true
    }

    static let permissionWords = "Needs permission: pages would leave this Mac."

    static func cannotRunHere(_ candidate: Components.Schemas.ModelCandidate) -> Bool {
        candidate.availability == .notHere
    }

    /// The rules refused it (`refused`: not enough memory, not the project's language, it runs in the cloud and
    /// pages stay here): nothing offers to use it, so a card never says "cannot" beside a button that does. A licence
    /// that is not open is the one refusal a press answers (choosing it accepts the licence, #5660 item 2).
    static func offersUse(_ candidate: Components.Schemas.ModelCandidate) -> Bool {
        guard !needsPermission(candidate) else { return false }
        guard !cannotRunHere(candidate), let refused = candidate.refused else { return !cannotRunHere(candidate) }
        return refused.contains("licence")
    }

    /// A refused card is not offered for download either, unless the engine says it runs elsewhere (a machine of the
    /// person's own), where the download is still the way to it.
    static func offersDownload(_ candidate: Components.Schemas.ModelCandidate) -> Bool {
        guard !needsPermission(candidate) else { return false }
        return offersUse(candidate) || candidate.availability == .elsewhere
    }

    /// Its why names Settings › AI ("add Claude (Anthropic) in Settings › AI first"): the card links there.
    static func asksForSettings(_ candidate: Components.Schemas.ModelCandidate) -> Bool {
        cannotRunHere(candidate) && candidate.availabilityWords.contains("Settings › AI")
    }

    /// The step's reader now (`chosen`, with `step`): marked, and offered no Use for This Step.
    static func isChosen(_ candidate: Components.Schemas.ModelCandidate) -> Bool {
        candidate.chosen == true
    }

    /// Why discovery offers it, when that says more than where it stands: a found reader's reason ("reads
    /// handwriting; lists Spanish"); nil for a card that only ships with Fichero or is on this Mac.
    static func whyOffered(_ candidate: Components.Schemas.ModelCandidate) -> String? {
        switch candidate.source {
        case .shipped, .installed: nil
        default: candidate.offeredBecause
        }
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
           "runs_where":"this_mac","availability":"ships","availability_words":"Available"},
          {"id":"mlx:hf/example/ocr-mlx@main","name":"Example OCR (MLX)","source":"hugging-face",
           "offered_because":"reads handwriting; lists Spanish; an MLX build this Mac runs",
           "pin":{"hf":"example/ocr-mlx","revision":"main"},"jobs":["read-a-line"],"licence":"cc-by-nc-4.0",
           "open_licence":false,"size":"size not stated",
           "measured":"unmeasured on your pages until a bake-off measures it","in_recipe_rules":true,"rule_rank":2,
           "installed":false,"runs_where":"this_mac","availability":"download","availability_words":"Download",
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

/// One HTR-United ground-truth dataset the engine kept for the project (#5571): what it may be used as, or the
/// licence to accept first. Taking one into the project is not built (`source.find.htr-united-and-tessdata`).
private struct HtrUnitedDatasetRow: View {
    let dataset: Components.Schemas.HtrUnitedDataset

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(dataset.title).font(.callout)
            Text(detail).font(.caption).foregroundStyle(.secondary)
        }
    }

    private var detail: String {
        let uses = dataset._as.map { $0 == "test-set" ? "test set" : $0 }
        let says = uses.isEmpty
            ? (dataset.accept ?? "Accept \(dataset.licence.name) to use it")
            : "Can be used as " + uses.formatted(.list(type: .and))
        return "HTR-United · \(says)"
    }
}

private extension Components.Schemas.HtrUnitedDataset {
    /// A missing url is stored as "", so the title joins it to tell two datasets apart.
    var key: String { title + "|" + url }
}
