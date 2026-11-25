import Foundation

/// One row of `segment.join_rows`: its lines and the one that keeps its id.
struct SegmentJoinRow: Encodable, Equatable {
    let segmentIds: [String]
    let keepId: String

    enum CodingKeys: String, CodingKey { case segmentIds = "segment_ids", keepId = "keep_id" }
}
