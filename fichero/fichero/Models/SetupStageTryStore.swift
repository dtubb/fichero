import FicheroAPIClient
import Foundation
import Observation
import OpenAPIRuntime

/// A stage's result on the sample pages (section 7c, #5668; `source.onboard.stages.samples-proposed`,
/// `.sample-result`): the 3 to 5 pages Fichero proposes (or the person chose), Try on These Pages, and what the try
/// made, per page. The engine runs it and keeps it beside the setup, never as the project's work; this store asks
/// and reads (`GET /api/recipes/samples`, `POST`/`GET /api/recipes/stages/{stage}/try`).
@MainActor
@Observable
final class SetupStageTryStore {
    let client: FicheroClient
    let stageId: String

    private(set) var samples: [Components.Schemas.SamplePage] = []
    /// What the last try left, or nil before one.
    private(set) var result: SetupStageTryResult?
    /// A try that would use the cloud says its cost first, in the engine's words; the person's yes runs it.
    private(set) var costQuestion: String?
    /// A try the engine refused, in its words.
    private(set) var refusal: String?
    private(set) var isTrying = false
    /// The candidates the person chose to compare (card ids, at most three); empty: the engine's own choice
    /// (`source.onboard.stages.compares-candidates`).
    var chosenCandidates: [String] = []

    /// How often a waiting try is asked again.
    var pollInterval: Duration = .seconds(3)

    init(client: FicheroClient, stageId: String) {
        self.client = client
        self.stageId = stageId
    }

    /// The sample pages, and the stage's last result.
    func load() async {
        do {
            if case .ok(let success) = try await client.api.getSamplesApiRecipesSamplesGet(query: .init(stage: stageId)) {
                samples = try success.body.json.pages
            }
        } catch {
            if error.isCancellationError { return }
            let words = await Self.engineWords(error)
            refusal = "Could not read the sample pages: \(words ?? error.localizedDescription)"
        }
        await readResult()
    }

    /// Try the stage on the samples. A cost is asked first; `costOK` is the person's yes to it.
    func tryIt(costOK: Bool = false) async {
        isTrying = true
        defer { isTrying = false }
        refusal = nil
        do {
            let response = try await client.api.tryStageApiRecipesStagesStageTryPost(
                path: .init(stage: stageId),
                body: .json(.init(costOk: costOK, candidates: StageCandidateChoice.request(chosenCandidates)))
            )
            switch response {
            case .ok(let success):
                costQuestion = nil
                result = try Self.decode(success.body.json)
                await follow()
            case .unprocessableContent:
                refusal = "Fichero could not try this stage on these pages."
            case .undocumented(let code, let payload):
                let words = await EngineErrorDetail.message(from: payload)
                if code == 402 {
                    costQuestion = words ?? "Trying this stage uses the cloud and has a cost."
                } else {
                    refusal = words ?? "Could not try this stage (HTTP \(code))."
                }
            }
        } catch {
            if error.isCancellationError { return }
            // A 422 the engine wrote in words is documented as a validation array, so the client throws; its sentence is in
            // the error's body (#5806).
            refusal = await Self.engineWords(error) ?? error.localizedDescription
        }
    }

    /// Ask again while the try is waiting or running, until it is done or failed.
    func follow() async {
        while result?.isUnderWay == true, !Task.isCancelled {
            try? await Task.sleep(for: pollInterval)
            await readResult()
        }
    }

    private func readResult() async {
        do {
            let response = try await client.api.stageTryResultApiRecipesStagesStageTryGet(path: .init(stage: stageId))
            switch response {
            case .ok(let success):
                result = try Self.decode(success.body.json)
            case .undocumented(let code, _) where code == 404:
                result = nil  // not tried yet (or no longer chosen): a normal state, never "still running" (#5806)
            default:
                break
            }
        } catch {
            if error.isCancellationError { return }
        }
    }

    /// Stop the try: its job is cancelled in Activity and the result reads as stopped.
    func stop() async {
        guard let jobId = result?.jobId else { return }
        do {
            _ = try await client.api.cancelJobApiActivityJobsJobIdCancelPost(path: .init(jobId: jobId))
        } catch {
            if error.isCancellationError { return }
            refusal = "Could not stop the try: \(error.localizedDescription)"
        }
        await readResult()
    }

    private static func engineWords(_ error: Error) async -> String? {
        guard let clientError = error as? ClientError, let body = clientError.responseBody,
              let data = try? await Data(collecting: body, upTo: 1 << 16) else { return nil }
        return EngineErrorDetail.message(from: data)
    }

    /// The engine's untyped result, read into the app's shape.
    static func decode<Body: Encodable>(_ body: Body) throws -> SetupStageTryResult {
        try JSONDecoder().decode(SetupStageTryResult.self, from: try JSONEncoder().encode(body))
    }

    /// A sample page's name, by id.
    func name(of pageId: String) -> String { samples.first { $0.id == pageId }?.name ?? pageId }
}

/// What a try on the samples made (`recipe/samples/<stage>.json`): per page, its readings, its segments by kind and
/// its statements; and the names found. Read and Find Lines are tried by the comparison of candidates, shown by the
/// page's comparison instead.
struct SetupStageTryResult: Decodable, Equatable {
    struct Reading: Decodable, Equatable {
        let kind: String?
        let level: String?
        let text: String
    }

    struct Page: Decodable, Equatable {
        let id: String
        let readings: [Reading]?
        let segments: [String: Int]?
        let statements: [String]?
        /// The page's lines and regions as the model drew them, normalised to the page (`compare-results-per-model`).
        let shapes: [Shape]?
    }

    /// One line or region a model found: its kind, its box (x, y, width, height) and its baseline, all 0 to 1.
    struct Shape: Decodable, Equatable {
        let kind: String
        let bbox: [Double]
        let baseline: [[Double]]?
    }

    struct Name: Decodable, Equatable {
        let name: String
        let type: String?
    }

    /// waiting, done or failed.
    let state: String
    let error: String?
    /// How it was tried, in words ("its own steps on a copy of these pages").
    let how: String?
    let perPage: [Page]?
    let names: [Name]?
    /// Organise's grouping of the samples into documents, when the try made one.
    let documents: [SetupStageProposedDocument]?
    /// Organise's entries (a diary's or a register's), each under the page it opens on.
    let entries: [SetupStageEntry]?
    /// The pages it was tried on, in order: for Organise, the run of consecutive pages.
    let pages: [String]?
    /// The comparison's id, for Read and Find Lines.
    let bakeoff: String?
    /// The same samples done by each of 2 or 3 candidates (`source.onboard.stages.compares-candidates`), when the
    /// engine compared them.
    let candidates: [StageCandidate]?
    /// The comparison of candidates a Read or Find Lines try started: its own state and why (the stage result stays
    /// "waiting" for the file; the comparison's job is what is running).
    let comparison: Comparison?
    /// What the whole try waits for, in the engine's words (the page images, the lane, a download).
    let waitingFor: String?
    /// The try's job in Activity, for Stop.
    let jobId: String?
    /// Where a try with no compared candidates is, on the result itself (`try-progress-in-place`).
    let progress: StageCandidate.Progress?

    struct Comparison: Decodable, Equatable {
        let state: String?
        let reason: String?
    }

    enum CodingKeys: String, CodingKey {
        case state, error, how, names, bakeoff, documents, entries, pages, candidates, comparison, progress
        case perPage = "per_page"
        case waitingFor = "waiting_for"
        case jobId = "job_id"
    }

    /// "Sentencia · 82% sure": a proposed document's kind and how sure, for the samples' grouping.
    static func detail(of document: SetupStageProposedDocument) -> String {
        let sure = document.confidence.map { $0.formatted(.percent.precision(.fractionLength(0))) + " sure" }
        return [document.kind, sure].compactMap { $0 }.joined(separator: " · ")
    }

    var isUnderWay: Bool { Self.underWay.contains(comparison?.state ?? state) }

    private static let underWay: Set<String> = ["waiting", "running"]

    /// What a try under way says beside its spinner: the engine's reason for the wait (a run held behind the imported
    /// pages names what it waits for, #5818), else a plain line; nil when it is not under way. A spinner alone read as
    /// "nothing happens".
    var underWayWords: String? {
        guard isUnderWay else { return nil }
        let waiting = waitingFor?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        if !waiting.isEmpty { return waiting }
        let reason = comparison?.reason?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        // Set Up is modal, so Activity cannot be reached from here: the try says where it is itself
        // (`source.onboard.stages.try-progress-in-place`).
        return reason.isEmpty ? "Working on it." : reason
    }

    /// "Kraken: page 2 of 5, finding lines" for each candidate under way, in the order compared.
    var progressLines: [String] {
        let each = (candidates ?? []).compactMap { $0.progressWords }
        if !each.isEmpty || !(candidates ?? []).isEmpty { return each }
        // No candidates compared: the try's own progress, with no model's name in front of it.
        guard let progress, progress.state == "running" || progress.state == "waiting", progress.total > 0 else { return [] }
        return ["Page \(min(progress.done + 1, progress.total)) of \(progress.total)" + (progress.step.map { ", \($0)" } ?? "")]
    }

    /// "Kraken: 27 lines, 3 regions · Apple Vision: 25 lines" for one page: each model's counts side by side
    /// (`source.onboard.stages.compare-results-per-model`); a model with nothing on that page is left out.
    func sideBySide(pageId: String) -> String {
        (candidates ?? []).compactMap { candidate in
            guard let page = candidate.perPage?.first(where: { $0.id == pageId }),
                  let counts = Self.countWords(page.segments ?? [:]) else { return nil }
            return "\(candidate.title): \(counts)"
        }.joined(separator: " · ")
    }

    /// "27 lines, 3 regions", "1 line": the engine's kinds with their plurals.
    static func countWords(_ segments: [String: Int]) -> String? {
        let parts = segments.filter { $0.value > 0 }.sorted { $0.key < $1.key }
            .map { "\($0.value) \($0.value == 1 ? $0.key : $0.key + "s")" }
        return parts.isEmpty ? nil : parts.joined(separator: ", ")
    }

    /// Why the try failed, in the engine's words, or nil when it did not: the stage's error, else the comparison's reason,
    /// else a plain sentence (a failed try is never blank).
    var failure: String? {
        guard state == "failed" || comparison?.state == "failed" else { return error }
        return error ?? comparison?.reason ?? "The try did not finish. Try it again."
    }

    /// One line per page for the page: what was read, how many lines and regions, how many statements.
    static func summary(of page: Page) -> String {
        var parts: [String] = []
        if let segments = countWords(page.segments ?? [:]) { parts.append(segments) }
        let statements = page.statements?.count ?? 0
        if statements > 0 { parts.append(statements == 1 ? "1 statement" : "\(statements) statements") }
        return parts.joined(separator: "; ")
    }
}

/// An entry Organise's Split into entries found on the samples: its name, its opening words, the page it opens on.
struct SetupStageEntry: Decodable, Equatable {
    let pageId: String
    let name: String
    let opening: String?

    enum CodingKeys: String, CodingKey {
        case name, opening
        case pageId = "page_id"
    }
}

/// Organise's try laid out over its run of pages (`finddocs.review.setup-page`): the pages in order, each proposed
/// document a group over its consecutive pages, every other page on its own, and the entries under their pages.
enum OrganiseTryLayout {
    enum Segment: Equatable {
        case document(SetupStageProposedDocument, pages: [String])
        case page(String)
    }

    /// The strip's segments, in the run's order: a document's pages that follow one another are one group.
    static func segments(pages: [String], documents: [SetupStageProposedDocument]) -> [Segment] {
        var owner: [String: Int] = [:]
        for (index, document) in documents.enumerated() {
            for pageId in document.pageIds where owner[pageId] == nil { owner[pageId] = index }
        }
        var segments: [Segment] = []
        for pageId in pages {
            guard let index = owner[pageId] else {
                segments.append(.page(pageId))
                continue
            }
            if case .document(let document, let held)? = segments.last, document == documents[index] {
                segments[segments.count - 1] = .document(document, pages: held + [pageId])
            } else {
                segments.append(.document(documents[index], pages: [pageId]))
            }
        }
        return segments
    }

    /// The entries under each page, in the engine's order.
    static func entries(_ entries: [SetupStageEntry]) -> [String: [SetupStageEntry]] {
        Dictionary(grouping: entries, by: \.pageId)
    }

    /// "Sentencia · 82% sure" over a document's group.
    static func caption(_ document: SetupStageProposedDocument) -> String {
        [document.name, SetupStageTryResult.detail(of: document)].filter { !$0.isEmpty }.joined(separator: " · ")
    }
}

/// A document Organise proposes on the samples (`finddocs.review.setup-page`): the pages it groups, in order.
struct SetupStageProposedDocument: Decodable, Equatable {
    let name: String
    let pageIds: [String]
    let kind: String?
    let confidence: Double?
    let reasons: [String]?

    enum CodingKeys: String, CodingKey {
        case name, kind, confidence, reasons
        case pageIds = "page_ids"
    }
}
