import Foundation

/// The Source view's edit verbs on a pass with NO artifact behind it -- every imported page (#5152)
/// -- as the audited segment actions, sent through `ActionsService.invokeAction`.
///
/// The artifact path (`PUT /api/artifacts/{id}/regions`) needs an artifact, and an imported pass has
/// none, so its boxes could be selected (ba9557474) but not moved, deleted or joined. Each call
/// carries the version the app READ (`expected_version`): an edit made against a copy somebody else
/// has since changed is refused by the engine rather than overwriting theirs. Pure: the rules live
/// where a test can reach them; `SegmentEditRunner` sends them.
enum SegmentEdit {
    /// One action to invoke: its registered name and its typed params.
    struct Call: Equatable {
        let action: String
        let params: Params
    }

    enum Params: Encodable, Equatable {
        case update(SegmentUpdateParams)
        case delete(SegmentDeleteParams)
        case merge(SegmentMergeParams)
        case updateMany(SegmentUpdateManyParams)

        func encode(to encoder: any Encoder) throws {
            switch self {
            case .update(let params): try params.encode(to: encoder)
            case .delete(let params): try params.encode(to: encoder)
            case .merge(let params): try params.encode(to: encoder)
            case .updateMany(let params): try params.encode(to: encoder)
            }
        }
    }

    /// A fact set on every selected segment at once -- the Segment menu (#5157;
    /// `source.editor.set-kind`, `set-direction`, `set-language-script`).
    enum Attribute: Equatable {
        case kind(String)
        case furniture(Bool)
        case direction(String)
        case language(String)
        case script(String)
    }

    /// The directions the engine accepts (`language_policy.DIRECTIONS`), in the menu's order.
    static let directions = ["ltr", "rtl", "ttb", "btt", "alternating", "follows-baseline"]

    /// A direction as people say it -- the Segment menu and the Inspector use the same words.
    static func directionName(_ direction: String) -> String {
        switch direction {
        case "ltr": "Left to Right"
        case "rtl": "Right to Left"
        case "ttb": "Top to Bottom"
        case "btt": "Bottom to Top"
        case "alternating": "Alternating (Boustrophedon)"
        case "follows-baseline": "Follows the Baseline"
        default: direction
        }
    }

    /// Why nothing is sent. Each is said, never guessed around.
    enum Refusal: Error, Equatable {
        /// A segment the list gave no version for (a provisional one): an edit could not be checked
        /// against a newer change, so it is not sent.
        case versionUnknown
        /// Join needs two or more; delete needs one.
        case tooFew
        /// A segment with extra shapes: moving only its box and outline would leave them behind.
        case hasExtraShapes
    }

    /// MOVE: the box goes to `rect`, and its outline moves by the same offset, so the two agree.
    static func move(_ segment: Segment, to rect: [Double]) -> Result<Call, Refusal> {
        guard let version = segment.version else { return .failure(.versionUnknown) }
        guard segment.anchor.shapes?.isEmpty ?? true else { return .failure(.hasExtraShapes) }
        let old = segment.anchor.rect ?? rect
        let deltaX = rect[0] - old[0]
        let deltaY = rect[1] - old[1]
        let polygon: [[Double]]? = segment.anchor.polygon.map { points in
            points.map { point in shifted(point, byX: deltaX, byY: deltaY) }
        }
        let anchor = SegmentAnchorParams(
            documentId: segment.anchor.documentId, pageId: segment.anchor.pageId,
            renditionId: segment.anchor.renditionId, space: segment.anchor.space, rect: rect,
            polygon: polygon, rotation: segment.anchor.rotation, granularity: segment.anchor.granularity
        )
        return .success(Call(
            action: "segment.update",
            params: .update(SegmentUpdateParams(segmentId: segment.id, expectedVersion: version, anchor: anchor))
        ))
    }

    /// SET one fact on every segment picked: ONE audited `segment.update_many`, so one ⌘Z undoes the
    /// whole selection's change.
    static func set(_ attribute: Attribute, on segments: [Segment]) -> Result<Call, Refusal> {
        guard !segments.isEmpty else { return .failure(.tooFew) }
        var updates: [SegmentAttributeUpdateParams] = []
        for segment in segments {
            guard let version = segment.version else { return .failure(.versionUnknown) }
            var update = SegmentAttributeUpdateParams(segmentId: segment.id, expectedVersion: version)
            switch attribute {
            case .kind(let kind): update.kind = kind
            case .furniture(let isFurniture): update.isFurniture = isFurniture
            case .direction(let direction): update.direction = direction
            case .language(let language): update.language = language
            case .script(let script): update.script = script
            }
            updates.append(update)
        }
        return .success(Call(
            action: "segment.update_many", params: .updateMany(SegmentUpdateManyParams(updates: updates))
        ))
    }

    /// DELETE the segments picked.
    static func delete(_ segments: [Segment]) -> Result<Call, Refusal> {
        guard !segments.isEmpty else { return .failure(.tooFew) }
        guard let versions = versions(of: segments) else { return .failure(.versionUnknown) }
        return .success(Call(
            action: "segment.delete",
            params: .delete(SegmentDeleteParams(segmentIds: segments.map(\.id), expectedVersions: versions))
        ))
    }

    /// JOIN the segments picked; the first picked is the one kept.
    static func join(_ segments: [Segment]) -> Result<Call, Refusal> {
        guard segments.count >= 2, let keep = segments.first else { return .failure(.tooFew) }
        guard let versions = versions(of: segments) else { return .failure(.versionUnknown) }
        return .success(Call(
            action: "segment.merge",
            params: .merge(SegmentMergeParams(
                segmentIds: segments.map(\.id), keepId: keep.id, expectedVersions: versions
            ))
        ))
    }

    /// One outline point moved; anything past x and y is kept as it was.
    private static func shifted(_ point: [Double], byX deltaX: Double, byY deltaY: Double) -> [Double] {
        guard point.count >= 2 else { return point }
        var moved: [Double] = point
        moved[0] += deltaX
        moved[1] += deltaY
        return moved
    }

    private static func versions(of segments: [Segment]) -> [String: Int]? {
        var versions: [String: Int] = [:]
        for segment in segments {
            guard let version = segment.version else { return nil }
            versions[segment.id] = version
        }
        return versions
    }
}

/// `segment.update`: the segment's anchor, moved.
struct SegmentUpdateParams: Encodable, Equatable {
    let segmentId: String
    let expectedVersion: Int
    let anchor: SegmentAnchorParams

    enum CodingKeys: String, CodingKey {
        case segmentId = "segment_id", expectedVersion = "expected_version", anchor
    }
}

/// The anchor fields a move rewrites or must keep; the rest are the segment's as read.
struct SegmentAnchorParams: Encodable, Equatable {
    let documentId: String?
    let pageId: String?
    let renditionId: String?
    let space: String?
    let rect: [Double]
    let polygon: [[Double]]?
    let rotation: Double?
    let granularity: String?

    enum CodingKeys: String, CodingKey {
        case documentId = "document_id", pageId = "page_id", renditionId = "rendition_id"
        case space, rect, polygon, rotation, granularity
    }
}

/// `segment.delete`: soft and undoable, every id with the version it was read at.
struct SegmentDeleteParams: Encodable, Equatable {
    let segmentIds: [String]
    let expectedVersions: [String: Int]

    enum CodingKeys: String, CodingKey {
        case segmentIds = "segment_ids", expectedVersions = "expected_versions"
    }
}

/// `segment.merge`: Join. The first segment picked is kept; the engine orders the text.
struct SegmentMergeParams: Encodable, Equatable {
    let segmentIds: [String]
    let keepId: String
    let expectedVersions: [String: Int]

    enum CodingKeys: String, CodingKey {
        case segmentIds = "segment_ids", keepId = "keep_id", expectedVersions = "expected_versions"
    }
}

/// `segment.update_many`: one row's part of a selection-wide attribute change. Only the fact being
/// set is sent; the others stay absent, which the engine reads as "unchanged".
struct SegmentAttributeUpdateParams: Encodable, Equatable {
    let segmentId: String
    let expectedVersion: Int
    var kind: String?
    var isFurniture: Bool?
    var direction: String?
    var language: String?
    var script: String?

    enum CodingKeys: String, CodingKey {
        case segmentId = "segment_id", expectedVersion = "expected_version", kind
        case isFurniture = "is_furniture", direction, language, script
    }

    func encode(to encoder: any Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(segmentId, forKey: .segmentId)
        try container.encode(expectedVersion, forKey: .expectedVersion)
        try container.encodeIfPresent(kind, forKey: .kind)
        try container.encodeIfPresent(isFurniture, forKey: .isFurniture)
        try container.encodeIfPresent(direction, forKey: .direction)
        try container.encodeIfPresent(language, forKey: .language)
        try container.encodeIfPresent(script, forKey: .script)
    }
}

struct SegmentUpdateManyParams: Encodable, Equatable {
    let updates: [SegmentAttributeUpdateParams]
}

/// Sends a `SegmentEdit.Call` through the audited choke point and registers ⌘Z for it by its own
/// audit id, then re-reads the page's segments so the boxes show the result.
@MainActor
struct SegmentEditRunner {
    let actionsService: ActionsService
    let store: SegmentStore

    /// Answers the audit id the edit wrote.
    @discardableResult
    func run(
        _ call: SegmentEdit.Call, documentId: String, actionName: String, undoManager: UndoManager?,
        afterChange: @escaping @MainActor () async -> Void = {}
    ) async throws -> String {
        let result = try await actionsService.invokeAction(name: call.action, params: call.params)
        let store = store
        let actionsService = actionsService
        ActionUndo.register(
            auditId: result.auditId, actionName: actionName, undoManager: undoManager,
            performUndo: { auditId in
                let next = try await actionsService.undoAction(auditId: auditId).auditId
                await store.load(documentId: documentId, force: true)
                await afterChange()
                return next
            }
        )
        await store.load(documentId: documentId, force: true)
        await afterChange()
        return result.auditId
    }
}
