import Foundation

/// `segment.join_rows`: each row's lines (the first kept) and every line's version as read.
struct SegmentJoinRowsRequest: Encodable, Equatable {
    let groups: [SegmentJoinRow]
    let expectedVersions: [String: Int]

    enum CodingKeys: String, CodingKey { case groups, expectedVersions = "expected_versions" }
}
