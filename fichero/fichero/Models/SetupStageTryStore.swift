import FicheroAPIClient
import Foundation
import Observation

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

    /// How often a waiting try is asked again.
    var pollInterval: Duration = .seconds(3)

    init(client: FicheroClient, stageId: String) {
        self.client = client
        self.stageId = stageId
    }

    /// The sample pages, and the stage's last result.
    func load() async {
        do {
            if case .ok(let success) = try await client.api.getSamplesApiRecipesSamplesGet() {
                samples = try success.body.json.pages
            }
        } catch {
            if error.isCancellationError { return }
            refusal = "Could not read the sample pages: \(error.localizedDescription)"
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
                path: .init(stage: stageId), body: .json(.init(costOk: costOK))
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
            refusal = error.localizedDescription
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
            if case .ok(let success) = try await client.api.stageTryResultApiRecipesStagesStageTryGet(
                path: .init(stage: stageId)
            ) {
                result = try Self.decode(success.body.json)
            }
        } catch {
            if error.isCancellationError { return }
        }
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
    /// The comparison's id, for Read and Find Lines.
    let bakeoff: String?

    enum CodingKeys: String, CodingKey {
        case state, error, how, names, bakeoff, documents
        case perPage = "per_page"
    }

    /// "Sentencia · 82% sure": a proposed document's kind and how sure, for the samples' grouping.
    static func detail(of document: SetupStageProposedDocument) -> String {
        let sure = document.confidence.map { $0.formatted(.percent.precision(.fractionLength(0))) + " sure" }
        return [document.kind, sure].compactMap { $0 }.joined(separator: " · ")
    }

    var isUnderWay: Bool { state == "waiting" || state == "running" }

    /// One line per page for the page: what was read, how many lines and regions, how many statements.
    static func summary(of page: Page) -> String {
        var parts: [String] = []
        let segments = (page.segments ?? [:]).sorted { $0.key < $1.key }.map { "\($0.value) \($0.key)" }
        if !segments.isEmpty { parts.append(segments.joined(separator: ", ")) }
        let statements = page.statements?.count ?? 0
        if statements > 0 { parts.append(statements == 1 ? "1 statement" : "\(statements) statements") }
        return parts.joined(separator: "; ")
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
