import FicheroAPIClient
import Foundation
import Observation

/// The model finder's store (#5611, `source.find.app-finder-three-hosts`): the reader candidates the
/// engine gathers for a job, scripts, languages and material (`GET /api/recipes/candidates`,
/// `source.find.by-need`), in the engine's order, with each source's line. The app never works out a
/// candidate, a rank or a fit; it shows what the engine answered.
///
/// One per project (`LibraryReference.modelFinderStore`), over THAT project's client, so the online
/// search runs as the project's own `find-models` job (#5594). Its progress is read from the project's
/// `ActivityStore` (the one poller of `GET /api/activity/jobs`), by the job's id, through `observe(_:)`
/// (`source.find.app-searching-line`); this store never polls.
@MainActor
@Observable
final class ModelFinderStore {
    /// What the finder asks for: the step's job, the project's scripts and languages, one material.
    struct Query: Equatable, Hashable {
        var job: String = ModelFinderStore.readingJob
        var scripts: [String]
        var languages: [String]
        var material: String = "handwriting"
        /// The recipe step the finder was opened beside: its reader is marked chosen and listed first (#5660).
        var step: String?
    }

    /// The job a query asks for when none is named. Which jobs the finder answers for is the engine's
    /// (`JobInfo.readsMaterial`, read through `RecipeSetupStore.readsMaterial`), never a list kept here.
    nonisolated static let readingJob = "read-a-line"
    /// The online search's job kind (`recipes/discovery.SEARCH_KIND`), as Activity lists it.
    nonisolated static let searchKind = "find-models"
    /// Activity snapshots a running search may be missing from before the finder reads again once
    /// (a search that ended between two polls is never listed): the bounded fallback.
    nonisolated static let unseenLimit = 3

    private(set) var query: Query?
    private(set) var candidates: [Components.Schemas.ModelCandidate] = []
    private(set) var sources: [Components.Schemas.CandidateSource] = []
    /// The online search the last read named (`search_job`), while it is waiting or running.
    private(set) var searchJob: Components.Schemas.SearchJob?
    /// What the running search is doing, from its Activity row's reason.
    private(set) var searchReason: String?
    /// Why the last online search failed, from Activity or the engine.
    private(set) var searchFailure: String?
    private(set) var isLoading = false
    var errorMessage: String?
    /// The project's downloads (#5620, `source.find.one-download-path`): the one download path, shared by the
    /// finder and Settings (setup downloads nothing: Start fetches what it needs, #5664); a card says what its download's job says.
    let downloads: ModelDownloads
    /// The HTR-United datasets kept for the query's languages and scripts (#5571), listed beside the sources.
    let htrUnited: HtrUnitedStore

    @ObservationIgnored private var seenInActivity = false
    @ObservationIgnored private var unseenSnapshots = 0

    private let client: FicheroClient

    init(client: FicheroClient, list: Components.Schemas.ModelCandidateList? = nil,
         downloads: ModelDownloads? = nil) {
        self.client = client
        self.downloads = downloads ?? ModelDownloads(client: client)
        self.htrUnited = HtrUnitedStore(client: client)
        if let list {
            candidates = list.items
            sources = list.sources
        }
        // A model downloaded here is now on this Mac: the cards say so (their `installed` and `download`).
        self.downloads.onFinished = { [weak self] _ in
            Task { await self?.reload() }
        }
    }

    /// Read the list again for the same query (a download finished), never searching online.
    func reload() async {
        guard query != nil else { return }
        await read(online: false)
    }

    /// Whether the online search is still going: the line "Searching online…" shows while it is.
    var isSearching: Bool { searchJob != nil }

    /// "Searching online…", with what the job says it is doing.
    var searchLine: String? {
        guard isSearching else { return nil }
        guard let reason = searchReason ?? searchJob?.reason, !reason.isEmpty else { return "Searching online…" }
        return "Searching online… \(reason)"
    }

    /// Read the candidates for this query (no online search). A new query replaces the list.
    func load(_ query: Query) async {
        if query != self.query {
            searchJob = nil
            searchFailure = nil
        }
        self.query = query
        await read(online: false)
        await htrUnited.load(languages: query.languages, scripts: query.scripts)
    }

    /// Search Online (`source.find.online-search-is-a-job`): the engine answers at once with what was
    /// kept and the search job; the finder then follows the job in Activity.
    func searchOnline() async {
        searchFailure = nil
        await read(online: true)
    }

    /// One Activity snapshot (`ActivityStore.backgroundJobs`). While a search runs: its row's reason is
    /// the line; a failed row's reason replaces the line and the list is read once more without
    /// `online` (never queuing a failing search again by itself); a row that has left the list has
    /// ended (done is not listed), and the list is read once more with `online`, which returns the
    /// finished job's findings without searching again (a search done within a day is reused).
    func observe(_ jobs: [ActivityJob]) async {
        guard let job = searchJob else { return }
        let row = jobs.first { $0.id == job.id }
            ?? jobs.first { $0.taskType == Self.searchKind && $0.id.hasPrefix("waiting:") }
        if let row {
            seenInActivity = true
            if row.state == .failed {
                searchJob = nil
                searchFailure = row.reason ?? "The online search failed."
                await read(online: false)
            } else {
                searchReason = row.reason
            }
            return
        }
        if !seenInActivity {
            // Not listed yet (the snapshot is older than the job), or it ended between two polls.
            unseenSnapshots += 1
            guard unseenSnapshots >= Self.unseenLimit else { return }
        }
        await read(online: true)
    }

    /// Download a candidate's model through the one download path (`ModelDownloads.start`, #5620), by the
    /// runtime and model its `download` names (#5612); the card then says what the download's job says, and
    /// Activity lists it. A candidate the engine names no download for (here already, fetched by the run, or
    /// run elsewhere) has no action.
    func download(_ candidate: Components.Schemas.ModelCandidate) async {
        guard let key = Self.downloadKey(candidate) else { return }
        await downloads.start(key, name: candidate.name)
    }

    /// The download a candidate names, as the one download path keys it; nil when it names none.
    static func downloadKey(_ candidate: Components.Schemas.ModelCandidate) -> ModelDownloads.Key? {
        candidate.download.map { ModelDownloads.Key(runtime: $0.runtime, model: $0.model) }
    }

    /// A source's line as the engine words it ("12 ship with Fichero", "0 on this Mac"); the two it words without
    /// naming the place ("Not searched") are said with it: "Kraken's model repository: not searched".
    static func sourceLine(_ source: Components.Schemas.CandidateSource) -> String {
        switch source.source {
        case .krakenRepository, .huggingFace: "\(sourceWords(source.source.rawValue)): \(source.detail)"
        default: source.detail
        }
    }

    /// Where a candidate came from, in words.
    static func sourceWords(_ source: String) -> String {
        switch source {
        case "shipped": "Ships with Fichero"
        case "installed": "Installed on this Mac"
        case "kraken-repository": "Kraken's model repository"
        case "hugging-face": "Found on Hugging Face"
        default: source
        }
    }

    private func read(online: Bool) async {
        guard let query else { return }
        guard !query.scripts.isEmpty else {
            errorMessage = "Name at least one script in the project's setup to find models for its steps."
            return
        }
        isLoading = true
        defer { isLoading = false }
        do {
            let response = try await client.api.modelCandidatesApiRecipesCandidatesGet(
                query: .init(
                    scripts: query.scripts.joined(separator: ","),
                    languages: query.languages.joined(separator: ","),
                    material: query.material,
                    job: query.job,
                    online: online,
                    step: query.step
                )
            )
            switch response {
            case .ok(let success):
                let list = try success.body.json
                candidates = list.items
                sources = list.sources
                errorMessage = nil
                follow(list.searchJob)
            case .unprocessableContent:
                errorMessage = "The engine would not look for models for these answers."
            case .undocumented(let code, _):
                errorMessage = "Could not find models (HTTP \(code))."
            }
        } catch {
            if error.isCancellationError { return }
            errorMessage = "Could not find models: \(error.localizedDescription)"
        }
    }

    /// Keep the search job while it is waiting or running; a failed one says why; a done one ends it.
    private func follow(_ job: Components.Schemas.SearchJob?) {
        seenInActivity = false
        unseenSnapshots = 0
        searchReason = nil
        guard let job else { searchJob = nil; return }
        switch job.state {
        case "waiting", "running", "paused":
            searchJob = job
        case "failed":
            searchJob = nil
            searchFailure = job.reason ?? "The online search failed."
        default:
            searchJob = nil
        }
    }
}
