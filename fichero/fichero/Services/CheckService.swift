import FicheroAPIClient
import Foundation

/// What `FlaggedLineStore` reads and writes: the check verdicts and a check run (#5446). The answers
/// are the routes' JSON as served, so a test drives the store with recorded route shapes.
@MainActor
protocol FlaggedLineTransport: AnyObject {
    /// `GET /api/check/verdicts?layer=readings`.
    func readingVerdicts() async throws -> Data
    /// `GET /api/check/runs/{id}`.
    func run(id: String) async throws -> Data
    /// `POST /api/check/verdicts`: a person's confirm of one reading of one line.
    func confirm(readingId: String, segmentId: String) async throws
}

/// The check routes through the generated client (`check.verdict`, `GET /api/check/verdicts`,
/// `GET /api/check/runs/{id}`). Both reads are untyped objects in the schema, so their JSON is handed
/// on as served and decoded once, in `FlaggedLines`.
@MainActor
final class CheckService: FlaggedLineTransport {
    let client: FicheroClient

    init(client: FicheroClient) {
        self.client = client
    }

    func readingVerdicts() async throws -> Data {
        // ponytail: the route has no page filter, so every reading verdict in the library is read and the
        // page's are picked out in `FlaggedLines`; a `document_id` query when libraries hold many checks.
        let response = try await client.api.listVerdictsApiCheckVerdictsGet(query: .init(layer: "readings"))
        switch response {
        case .ok(let okResponse):
            return try JSONEncoder().encode(okResponse.body.json)
        case .unprocessableContent:
            throw SegmentServiceError.unexpectedResponse(422)
        case .undocumented(let statusCode, _):
            throw SegmentServiceError.unexpectedResponse(statusCode)
        }
    }

    func run(id: String) async throws -> Data {
        let response = try await client.api.checkRunStatusApiCheckRunsJobIdGet(path: .init(jobId: id))
        switch response {
        case .ok(let okResponse):
            return try JSONEncoder().encode(okResponse.body.json)
        case .unprocessableContent:
            throw SegmentServiceError.unexpectedResponse(422)
        case .undocumented(let statusCode, _):
            throw SegmentServiceError.unexpectedResponse(statusCode)
        }
    }

    func confirm(readingId: String, segmentId: String) async throws {
        let response = try await client.api.recordVerdictApiCheckVerdictsPost(body: .json(.init(
            layer: .readings, targetId: readingId, verdict: .confirm,
            reasons: "A person looked at the line and confirmed its reading", segmentId: segmentId
        )))
        switch response {
        case .ok:
            return
        case .unprocessableContent:
            throw SegmentServiceError.unexpectedResponse(422)
        case .undocumented(let statusCode, _):
            throw SegmentServiceError.unexpectedResponse(statusCode)
        }
    }
}
