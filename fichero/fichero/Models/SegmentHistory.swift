import FicheroAPIClient
import Foundation

/// One segment's own history (#5163; `source.segment.versioned-alone`): every earlier version the
/// engine kept (`GET /api/segments/{id}/versions`), each described by what changed AFTER it, and the
/// restore the Inspector's Making section sends (`segment.restore_version`, ⌘Z by its audit id). Also
/// the baseline, said in words. Pure: the rules live where a test can reach them.
enum SegmentHistory {
    /// The facts a version records that a person can see change.
    struct State: Equatable {
        var kind: String
        var rect: [Double]?
        var polygon: [[Double]]?
        var baseline: [[Double]]?
        var language: String?
        var script: String?
        var direction: String?
        var deleted = false
    }

    struct Version: Identifiable, Equatable {
        let id: String
        let version: Int
        let state: State
        let actor: String?
        let reason: String?
        let createdAt: Date?
    }

    /// What changed from `before` to `after`, in the order a person reads a box: where, what, how.
    /// Empty when nothing visible changed (a change to a field the Inspector does not show).
    static func changes(from before: State, to after: State) -> [String] {
        var said: [String] = []
        if before.deleted != after.deleted { said.append(after.deleted ? "deleted" : "restored") }
        if before.rect != after.rect || before.polygon != after.polygon { said.append("moved or reshaped") }
        if before.baseline != after.baseline { said.append("baseline changed") }
        if before.kind != after.kind { said.append("kind \(before.kind) → \(after.kind)") }
        for (name, old, new) in [
            ("language", before.language, after.language), ("script", before.script, after.script),
            ("direction", before.direction, after.direction)
        ] where old != new {
            said.append("\(name) \(old ?? "unset") → \(new ?? "unset")")
        }
        return said
    }

    /// Each kept version, newest first, with what the change after it did (to the next version, or to
    /// the live row for the newest).
    static func rows(_ versions: [Version], live: State) -> [(version: Version, then: [String])] {
        let sorted = versions.sorted { $0.version < $1.version }
        let nextStates = sorted.dropFirst().map(\.state) + [live]
        return zip(sorted, nextStates).map { (version: $0, then: changes(from: $0.state, to: $1)) }.reversed()
    }

    /// The restore the Section sends: back to `version`, checked against the version it READ.
    static func restore(_ version: Version, of segment: Segment) -> SegmentRestoreVersionRequest? {
        guard let current = segment.version, version.version < current else { return nil }
        return SegmentRestoreVersionRequest(segmentId: segment.id, version: version.version, expectedVersion: current)
    }

    /// The baseline in words: straight or curved, and how many points. Curved when any inner point lies
    /// off the line from the first to the last by more than `tolerance` (normalized page units).
    static func baselineDescription(_ baseline: [[Double]]?, tolerance: Double = 0.002) -> String? {
        guard let points = baseline?.filter({ $0.count >= 2 }), points.count >= 2,
              let first = points.first, let last = points.last else { return nil }
        let deltaX = last[0] - first[0], deltaY = last[1] - first[1]
        let length = (deltaX * deltaX + deltaY * deltaY).squareRoot()
        let curved = length > 0 && points.dropFirst().dropLast().contains { point in
            abs(deltaY * (point[0] - first[0]) - deltaX * (point[1] - first[1])) / length > tolerance
        }
        return "\(curved ? "Curved" : "Straight") baseline, \(points.count) points"
    }

    static func state(of segment: Segment) -> State {
        State(
            kind: segment.kind, rect: segment.anchor.rect, polygon: segment.anchor.polygon, baseline: segment.baseline,
            language: segment.language, script: segment.script, direction: segment.direction
        )
    }
}

/// `segment.restore_version`: the segment back to one of its kept versions.
struct SegmentRestoreVersionRequest: Encodable, Equatable {
    let segmentId: String
    let version: Int
    let expectedVersion: Int

    enum CodingKeys: String, CodingKey {
        case segmentId = "segment_id", version, expectedVersion = "expected_version"
    }
}

extension SegmentService {
    /// One segment's kept versions (`GET /api/segments/{id}/versions`). Empty for an id this build
    /// cannot resolve (a 422, e.g. a provisional segment, which has no history of its own).
    func versions(segmentId: String) async throws -> [SegmentHistory.Version] {
        let response = try await client.api.listSegmentVersionsApiSegmentsSegmentIdVersionsGet(
            path: .init(segmentId: segmentId)
        )
        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json.items.map { item in
                let anchor = SourceAnchorValue(generated: item.anchor)
                return SegmentHistory.Version(
                    id: item.id ?? "\(segmentId)-v\(item.version)", version: item.version,
                    state: SegmentHistory.State(
                        kind: item.kind, rect: anchor.rect, polygon: anchor.polygon, baseline: item.baseline,
                        language: item.language, script: item.script, direction: item.direction,
                        deleted: item.deleted ?? false
                    ),
                    actor: item.actor, reason: item.reason, createdAt: item.createdAt
                )
            }
        case .unprocessableContent:
            return []
        case .undocumented(let statusCode, _):
            throw SegmentServiceError.unexpectedResponse(statusCode)
        }
    }
}
