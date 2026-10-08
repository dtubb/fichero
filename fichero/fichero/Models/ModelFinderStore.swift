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
    /// Candidates whose download was asked for here, by id; Activity shows the download job.
    private(set) var downloading: Set<String> = []
    var errorMessage: String?

    @ObservationIgnored private var seenInActivity = false
    @ObservationIgnored private var unseenSnapshots = 0

    private let client: FicheroClient

    init(client: FicheroClient, list: Components.Schemas.ModelCandidateList? = nil) {
        self.client = client
        if let list {
            candidates = list.items
            sources = list.sources
        }
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

    /// Download a candidate's model through the one download route
    /// (`POST /api/local-models/download/{runtime}/{model}`), by the runtime and model its `download`
    /// names (#5612); the card says Downloading… and Activity shows the job. A candidate the engine
    /// names no download for (here already, fetched by the run, or run elsewhere) has no action.
    func download(_ candidate: Components.Schemas.ModelCandidate) async {
        guard let download = candidate.download else { return }
        do {
            let response = try await client.api.downloadModelApiLocalModelsDownloadModelTypeModelIdPost(
                path: .init(modelType: download.runtime, modelId: download.model)
            )
            switch response {
            case .ok:
                downloading.insert(candidate.id)
            case .unprocessableContent:
                errorMessage = "Could not download \(candidate.name)."
            case .undocumented(let code, _):
                errorMessage = "Could not download \(candidate.name) (HTTP \(code))."
            }
        } catch {
            if error.isCancellationError { return }
            errorMessage = "Could not download \(candidate.name): \(error.localizedDescription)"
        }
    }

    /// Whether the candidate's model is on this Mac, in words (`installed`); nil where the engine says
    /// nothing is downloaded first (a Kraken reader the run fetches, a cloud model).
    static func installedWords(_ installed: Bool?) -> String? {
        switch installed {
        case true?: "On this Mac"
        case false?: "Not on this Mac yet"
        case nil: nil
        }
    }

    /// Where a candidate runs, in words (`runs_where`, the places of `llm/places.py`).
    static func placeWords(_ place: String) -> String {
        switch place {
        case "this_mac": "Runs on this Mac"
        case "own_machine": "Runs on a machine of yours"
        case "provider": "Runs at the provider"
        default: place
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
            errorMessage = "Name at least one script in the project's setup to find readers."
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
                    online: online
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
                errorMessage = "The engine would not look for readers for these answers."
            case .undocumented(let code, _):
                errorMessage = "Could not find readers (HTTP \(code))."
            }
        } catch {
            if error.isCancellationError { return }
            errorMessage = "Could not find readers: \(error.localizedDescription)"
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
