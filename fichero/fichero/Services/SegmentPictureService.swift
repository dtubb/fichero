import FicheroAPIClient
import Foundation

/// One segment's picture, cut from its page to its shape by the engine (`GET
/// /api/segments/{id}/picture`, `segment-editor.md` "Segment pictures"): what the Segments pane's
/// strip and grid show. PNG bytes, or nil when the engine has no image to cut from.
@MainActor
struct SegmentPictureService {
    let client: FicheroClient

    /// The picture at `size` points on its long side.
    func picture(segmentId: String, size: Int = 240) async throws -> Data? {
        let response = try await client.api.getSegmentPictureApiSegmentsSegmentIdPictureGet(
            path: .init(segmentId: segmentId), query: .init(size: size), headers: .init(accept: [.init(contentType: .png)])
        )
        switch response {
        case .ok(let okResponse):
            switch okResponse.body {
            case .png(let body): return try await Data(collecting: body, upTo: 16 * 1024 * 1024)
            case .json: return nil
            }
        case .unprocessableContent:
            return nil
        case .undocumented:
            // No page image to cut from (a 404) is a picture that does not exist, not a failure.
            return nil
        }
    }
}
