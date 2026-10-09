import FicheroAPIClient
import Foundation
import Observation

/// The one way the app downloads a model (#5620, `source.find.one-download-path`): Set Up… › Ready (To download
/// first), the model finder (the Inspector, setup and Settings) and Settings' model rows all call `start`, which
/// calls the one route (`POST /api/local-models/download/{runtime}/{model}`, the `model.download` action). The engine
/// queues a `download-model` job, which Activity lists; this store follows that one job by its id
/// (`GET /api/activity/jobs/{id}`) while it runs, so the row that asked says what the job says ("Downloading
/// Qwen2.5-VL 7B: 1.2 GB of 5.6 GB"), and a failure says why, in the engine's words. When the job is done the
/// engine says `model.installed`, and setup's plan reads itself again (`RecipeSetupStore.modelInstalled`).
///
/// One per project (`ModelFinderStore.downloads`), over THAT project's client, so the job is the project's and its
/// Activity lists it; Settings uses the open project's, else the global library's (`forSettings`).
@MainActor
@Observable
final class ModelDownloads {
    /// A model, as the route names it: its runtime (mlx, spacy, kraken, whisper, embeddings) and its id there.
    struct Key: Hashable, Sendable {
        let runtime: String
        let model: String
    }

    /// Where a download asked for here stands.
    enum State: Equatable {
        /// Asked for; the engine has not answered yet.
        case starting
        /// The job is waiting or running; what it says it is doing.
        case running(String)
        /// It failed, or was refused before it was queued; why, in words.
        case failed(String)
        /// The model is here.
        case done
    }

    private(set) var states: [Key: State] = [:]
    /// How many downloads asked for here have finished: a host that lists models reads them again when it moves.
    private(set) var finished = 0
    /// The owner's own cue that one finished (the finder reads its candidates again).
    @ObservationIgnored var onFinished: ((Key) -> Void)?

    @ObservationIgnored private var jobIds: [Key: String] = [:]
    @ObservationIgnored private var names: [Key: String] = [:]
    @ObservationIgnored private var follows: [Key: Task<Void, Never>] = [:]

    private let client: FicheroClient
    /// How often a running download's job is read: minutes-long downloads need no faster.
    private let followInterval: Duration

    init(client: FicheroClient, followInterval: Duration = .seconds(2)) {
        self.client = client
        self.followInterval = followInterval
    }

    func state(_ key: Key) -> State? { states[key] }

    /// Whether a download of this model is asked for and not ended: its button is not offered again.
    func isActive(_ key: Key) -> Bool {
        switch states[key] {
        case .starting?, .running?: true
        default: false
        }
    }

    /// The row's line for this model: what the job is doing, or why it failed; nil when nothing was asked here or
    /// it is done (the row then says what the engine lists).
    func line(_ key: Key) -> String? {
        switch states[key] {
        case .starting?: "Starting the download…"
        case .running(let words)?: words
        case .failed(let why)?: why
        case .done?, nil: nil
        }
    }

    /// Download `key` (the one code path). `name` is how the row calls the model, for the words of a refusal.
    /// A second press while one runs does nothing; a press after a failure tries again.
    func start(_ key: Key, name: String) async {
        guard !isActive(key) else { return }
        names[key] = name
        states[key] = .starting
        do {
            let response = try await client.api.downloadModelApiLocalModelsDownloadModelTypeModelIdPost(
                path: .init(modelType: key.runtime, modelId: key.model)
            )
            switch response {
            case .ok(let success):
                let started = try success.body.json
                guard let jobId = started.jobId else {
                    states[key] = .failed("Could not download \(name): the engine queued no job to follow.")
                    return
                }
                jobIds[key] = jobId
                states[key] = .running("Waiting to download \(name)…")
                follow(key, jobId: jobId)
            case .unprocessableContent(let error):
                let detail = (try? error.body.json)?.detail?.description
                states[key] = .failed("Could not download \(name): \(detail ?? "the engine refused the request").")
            case .undocumented(let code, let payload):
                let detail = await EngineErrorDetail.message(from: payload) ?? "HTTP \(code)"
                states[key] = .failed("Could not download \(name): \(detail)")
            }
        } catch {
            if error.isCancellationError {
                states[key] = nil
                return
            }
            states[key] = .failed("Could not download \(name): \(error.localizedDescription)")
        }
    }

    /// Read the download's job once and say where it stands. Returns whether it is still going.
    @discardableResult
    func refresh(_ key: Key) async -> Bool {
        guard let jobId = jobIds[key] else { return false }
        let name = names[key] ?? key.model
        do {
            switch try await client.api.getJobTreeApiActivityJobsJobIdGet(path: .init(jobId: jobId)) {
            case .ok(let success):
                let node = try success.body.json
                return apply(state: node.state, reason: node.reason, to: key, name: name)
            case .unprocessableContent:
                return true
            case .undocumented(let code, _):
                if code == 404 {
                    states[key] = .failed("Could not download \(name): its job is no longer in this project.")
                    return false
                }
                // A read that failed is not the download failing: the next read tries again.
                return true
            }
        } catch {
            // The engine restarting or a dropped connection: the next read tries again; a cancelled one ends.
            return !error.isCancellationError
        }
    }

    /// The job's state and reason, as the job row has them, applied to the model's state. Returns whether it is
    /// still going.
    func apply(state: String, reason: String?, to key: Key, name: String) -> Bool {
        switch state {
        case "done", "completed":
            states[key] = .done
            finished += 1
            onFinished?(key)
            return false
        case "failed", "cancelled":
            let why = reason.flatMap { $0.isEmpty ? nil : $0 } ?? "the download stopped"
            states[key] = .failed("Could not download \(name): \(why)")
            return false
        default:
            let words = reason.flatMap { $0.isEmpty ? nil : $0 } ?? "Downloading \(name)…"
            states[key] = .running(words)
            return true
        }
    }

    private func follow(_ key: Key, jobId: String) {
        follows[key]?.cancel()
        follows[key] = Task { [weak self] in
            while !Task.isCancelled {
                guard let interval = self?.followInterval else { return }
                try? await Task.sleep(for: interval)
                guard !Task.isCancelled, let self else { return }
                if !(await self.refresh(key)) { return }
            }
        }
    }

    /// Settings' downloads: the open project's (its Activity lists the job), else the global library's.
    static func forSettings(_ libraryManager: LibraryManager) -> ModelDownloads? {
        let library = libraryManager.currentLibraryId.flatMap { libraryManager.getLibrary(id: $0) }
            ?? libraryManager.globalLibrary
        return library?.modelFinderStore.downloads
    }

    /// The download runtime of a Settings catalog row's provider (`ProviderType` rawValue): this Mac's MLX
    /// server's models download as `mlx`; spaCy, Kraken and Whisper under their own names.
    static func runtime(ofProvider providerType: String) -> String {
        providerType == "omlx" ? "mlx" : providerType
    }

    /// A Settings catalog row's model, as the one download path keys it.
    static func key(_ entry: Components.Schemas.LocalModelCatalogEntry) -> Key {
        Key(runtime: runtime(ofProvider: entry.providerType.rawValue), model: entry.modelId)
    }
}
