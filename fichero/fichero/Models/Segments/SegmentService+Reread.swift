import FicheroAPIClient
import Foundation

/// The engine's answer to "these lines were edited" (`POST /api/recipes/project/reread-edited`).
struct SegmentRereadAnswer: Equatable {
    /// Lines whose reading a paid cloud model made: not run, to be read again by the person.
    let stale: [String]
    /// Lines a local re-read was queued for.
    let started: [String]
}

extension SegmentService {
    func rereadEdited(segmentIds: [String]) async throws -> SegmentRereadAnswer {
        let response = try await client.api.rereadEditedSegmentsApiRecipesProjectRereadEditedPost(
            body: .json(.init(segmentIds: segmentIds))
        )
        switch response {
        case .ok(let okResponse):
            let body = try okResponse.body.json
            return SegmentRereadAnswer(stale: body.stale.map(\.segmentId), started: body.started.map(\.segmentId))
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw SegmentServiceError.serverError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw SegmentServiceError.unexpectedResponse(statusCode)
        }
    }
}
