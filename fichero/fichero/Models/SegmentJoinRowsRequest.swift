import Foundation

/// `segment.join_rows`: each row's lines (the first kept) and every line's version as read.
struct SegmentJoinRowsRequest: Encodable, Equatable {
    struct Row: Encodable, Equatable {
        let segmentIds: [String]
        let keepId: String

        enum CodingKeys: String, CodingKey { case segmentIds = "segment_ids", keepId = "keep_id" }
    }

    let groups: [Row]
    let expectedVersions: [String: Int]

    enum CodingKeys: String, CodingKey { case groups, expectedVersions = "expected_versions" }
}
