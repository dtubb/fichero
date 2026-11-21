import Foundation

/// `reading_order.move`: rows dropped between rows of the segment list, in their list order, put after `afterSegmentId`
/// (none: first) under `parentSegmentId` (none: the order's top level).
struct ReadingOrderMoveRequest: Encodable, Equatable {
    let orderId: String
    let segmentIds: [String]
    let parentSegmentId: String?
    let afterSegmentId: String?

    enum CodingKeys: String, CodingKey {
        case orderId = "order_id", segmentIds = "segment_ids", parentSegmentId = "parent_segment_id"
        case afterSegmentId = "after_segment_id"
    }

    func encode(to encoder: any Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(orderId, forKey: .orderId)
        try container.encode(segmentIds, forKey: .segmentIds)
        try container.encodeIfPresent(parentSegmentId, forKey: .parentSegmentId)
        try container.encodeIfPresent(afterSegmentId, forKey: .afterSegmentId)
    }
}
