import Foundation

/// The segment editor's tools as audited calls (`docs/contributor_manual/specs/ui/segment-editor.md`): Redraw
/// Outline from Baseline and the Knife. Pure, like the rest of `SegmentEdit`; the Preview sends them.
extension SegmentEdit {
    /// REDRAW each selected line's outline from its baseline and the page image
    /// (`segment-editor.regenerate-polygon-from-baseline`): one `segment.regenerate_outline`, one undo. A line with
    /// no baseline is refused here, as the engine would refuse it, so the menu can say why before anything is sent.
    static func redrawOutline(_ segments: [Segment]) -> Result<Call, Refusal> {
        guard !segments.isEmpty else { return .failure(.tooFew) }
        guard segments.allSatisfy(hasBaseline) else { return .failure(.noBaseline) }
        guard let versions = versions(of: segments) else { return .failure(.versionUnknown) }
        return .success(Call(
            action: "segment.regenerate_outline",
            params: .regenerateOutline(SegmentRegenerateOutlineRequest(
                segmentIds: segments.map(\.id), expectedVersions: versions
            ))
        ))
    }

    /// The KNIFE (`segment-editor.split-knife`): one stroke, sent once in the frame it was drawn in (the page's
    /// fractions), with the versions of every line of the shown pass (`passId`) whose box it reaches; the engine
    /// refuses lines of two passes in one stroke. The engine decides which it crosses: a line it only grazes is left
    /// alone and named in the answer. Regions of the shown pass are offered too (`kind == "region"`, no baseline
    /// needed): the engine cuts one's polygon along the stroke. Lines with no baseline or no version are not
    /// offered; a stroke that reaches no
    /// line, or a click with no length, sends nothing, and one that reaches only lines with no baseline is refused as
    /// `.noBaseline` (`segment-editor.edge.no-baseline`).
    static func knife(_ stroke: [[Double]], over lines: [Segment], onPass passId: String?) -> Result<Call, Refusal> {
        guard stroke.count >= 2, let reach = bounds(of: stroke) else { return .failure(.tooFew) }
        let reached = lines.filter { line in
            guard line.passId == passId, let rect = line.anchor.rect, rect.count >= 4 else { return false }
            return rect[0] <= reach[2] && reach[0] <= rect[0] + rect[2] && rect[1] <= reach[3] && reach[1] <= rect[1] + rect[3]
        }
        guard !reached.isEmpty else { return .failure(.tooFew) }
        let cuttable = reached.filter { $0.kind == "region" || hasBaseline($0) }
        guard !cuttable.isEmpty else { return .failure(.noBaseline) }
        let versioned = cuttable.filter { $0.version != nil }
        guard !versioned.isEmpty, let versions = versions(of: versioned) else { return .failure(.versionUnknown) }
        return .success(Call(
            action: "segment.split",
            params: .knife(SegmentKnifeRequest(cutPath: stroke, expectedVersions: versions))
        ))
    }

    /// SPLIT one line at a point (`segment-editor.split-at-a-point`): the Knife's call with a two-point stroke through
    /// the point's foot on the baseline, at right angles to it, reaching past the line's box on both sides.
    static func splitAtPoint(_ line: Segment, at point: [Double]) -> Result<Call, Refusal> {
        guard let baseline = line.baseline, baseline.count >= 2 else { return .failure(.noBaseline) }
        guard point.count >= 2, let foot = footOnBaseline(baseline, point) else { return .failure(.tooFew) }
        guard let version = line.version else { return .failure(.versionUnknown) }
        let height = max(line.anchor.rect.flatMap { $0.count >= 4 ? $0[3] : nil } ?? 0.02, 0.01)
        let reach = height * 2
        let stroke = [
            [foot.pointX - foot.normalX * reach, foot.pointY - foot.normalY * reach],
            [foot.pointX + foot.normalX * reach, foot.pointY + foot.normalY * reach]
        ]
        return .success(Call(
            action: "segment.split", params: .knife(SegmentKnifeRequest(cutPath: stroke, expectedVersions: [line.id: version]))
        ))
    }

    /// The point on a baseline nearest a given point, and the unit normal of the stretch it lies on.
    struct BaselineFoot {
        let pointX: Double, pointY: Double, normalX: Double, normalY: Double
        let distance: Double
    }

    /// The point on the baseline nearest `point`, and the unit normal of the stretch it lies on.
    static func footOnBaseline(_ baseline: [[Double]], _ point: [Double]) -> BaselineFoot? {
        var best: BaselineFoot?
        for (start, end) in zip(baseline, baseline.dropFirst()) where start.count >= 2 && end.count >= 2 {
            let deltaX = end[0] - start[0], deltaY = end[1] - start[1]
            let length = hypot(deltaX, deltaY)
            guard length > 0 else { continue }
            let along = min(max(((point[0] - start[0]) * deltaX + (point[1] - start[1]) * deltaY) / (length * length), 0), 1)
            let footX = start[0] + deltaX * along, footY = start[1] + deltaY * along
            let distance = hypot(point[0] - footX, point[1] - footY)
            if distance < (best?.distance ?? .infinity) {
                best = BaselineFoot(pointX: footX, pointY: footY, normalX: -deltaY / length, normalY: deltaX / length, distance: distance)
            }
        }
        return best
    }

    /// What the page says when a tool's edit was refused before anything was sent, never silent (#6734).
    static func notSentWords(_ name: String, _ refusal: Refusal) -> String {
        let why: String = switch refusal {
        case .tooFew: "nothing to act on: the stroke reaches no segment it can change"
        case .versionUnknown: "the segments are not saved yet"
        case .noBaseline: "a line has no baseline"
        case .noOrder: "this page has no reading order"
        }
        return "\(name): \(why)."
    }

    /// What the Knife says when it is done: how many lines it cut, and how many under the stroke it left alone
    /// (crossed nowhere on the baseline, or no baseline to cut); nil when there is nothing worth saying.
    static func knifeNotice(cut: Int, leftAlone: Int) -> String? {
        guard leftAlone > 0 else { return nil }
        let cutWords = cut == 1 ? "Cut 1 line" : "Cut \(cut) lines"
        let aloneWords = leftAlone == 1
            ? "1 line the stroke did not cross was left alone"
            : "\(leftAlone) lines the stroke did not cross were left alone"
        return "\(cutWords); \(aloneWords)"
    }

    /// The tolerance Simplify uses from the menu, in image pixels: enough to drop a traced staircase, not the ink's
    /// shape.
    static let simplifyTolerance = 2.0

    /// SIMPLIFY the selected segments' outlines and baselines (`segment-editor.vertices`): one `segment.simplify`,
    /// one undo. The engine leaves a shape already that simple as it is.
    static func simplify(_ segments: [Segment], tolerance: Double = simplifyTolerance) -> Result<Call, Refusal> {
        guard !segments.isEmpty else { return .failure(.tooFew) }
        guard let versions = versions(of: segments) else { return .failure(.versionUnknown) }
        return .success(Call(
            action: "segment.simplify",
            params: .simplify(SegmentSimplifyRequest(
                segmentIds: segments.map(\.id), expectedVersions: versions, tolerance: tolerance
            ))
        ))
    }

    /// MOVE the selection by one offset (`segment-editor.group-drag`): ONE `segment.translate`, outlines, shapes and
    /// baselines moving with their boxes, one ⌘Z. The engine holds the offset at the page's edge for the whole group.
    static func translate(_ segments: [Segment], by offset: [Double]) -> Result<Call, Refusal> {
        guard !segments.isEmpty, offset.count >= 2 else { return .failure(.tooFew) }
        guard segments.allSatisfy({ $0.version != nil }) else { return .failure(.versionUnknown) }
        return .success(Call(action: "segment.translate", params: .translate(SegmentTranslateRequest(
            segments: segments.compactMap { segment in
                segment.version.map { SegmentReparentRequest.Item(segmentId: segment.id, expectedVersion: $0) }
            },
            across: offset[0], down: offset[1]
        ))))
    }

    /// MOVE A CUT (`segment-editor.cut-marks-editable`): the boundary between two pieces of a line, to `at` along the line's
    /// baseline (`place`), as ONE `segment.move_cut`; the engine re-cuts both and marks the cut a person's. One undo.
    static func moveCut(firstId: String, secondId: String, place: Double, versions: [String: Int]) -> Result<Call, Refusal> {
        guard let first = versions[firstId], let second = versions[secondId] else { return .failure(.versionUnknown) }
        return .success(Call(action: "segment.move_cut", params: .moveCut(SegmentMoveCutRequest(
            firstId: firstId, secondId: secondId, place: place, expectedVersions: [firstId: first, secondId: second]
        ))))
    }

    /// ORDER BY CLICKING (`segment-editor.order-by-clicking`): the clicks, in one order, as one `reading_order.sequence`,
    /// one undo. The order is the pass's `as-written` (the order the page draws; a named order the Segments pane chose is
    /// not known here yet).
    static func sequence(
        _ clicks: [String], after: String?, passId: String, orders: [ReadingOrderSummary]
    ) -> Result<Call, Refusal> {
        guard !clicks.isEmpty else { return .failure(.tooFew) }
        guard let order = orders.first(where: { $0.passId == passId && $0.name == "as-written" }) else {
            return .failure(.noOrder)
        }
        return .success(Call(action: "reading_order.sequence", params: .sequence(ReadingOrderSequenceRequest(
            orderId: order.id, segmentIds: clicks, afterSegmentId: after
        ))))
    }

    /// CUT WORDS on the selected lines (`segment-editor.cut-words-from-positions`): one `segment.cut_words`, one undo.
    /// The engine cuts each line's reading at its spaces, from the recogniser's positions or the ink, and says which
    /// lines it could not cut.
    static func cutWords(_ lines: [Segment]) -> Result<Call, Refusal> {
        guard !lines.isEmpty else { return .failure(.tooFew) }
        guard lines.allSatisfy(hasBaseline) else { return .failure(.noBaseline) }
        guard let versions = versions(of: lines) else { return .failure(.versionUnknown) }
        return .success(Call(
            action: "segment.cut_words",
            params: .cutWords(SegmentCutWordsRequest(segmentIds: lines.map(\.id), expectedVersions: versions))
        ))
    }

    /// JOIN a word broken at a line's end (`segment-editor.edge.word-across-lines`): its two pieces as ONE `segment.merge`
    /// keeping both shapes, the first piece kept, the second moved into its line; one undo.
    static func joinBrokenWord(_ first: Segment, _ second: Segment) -> Result<Call, Refusal> {
        guard let versions = versions(of: [first, second]) else { return .failure(.versionUnknown) }
        var request = SegmentMergeRequest(segmentIds: [first.id, second.id], keepId: first.id, expectedVersions: versions)
        request.keepShapes = true
        request.moveIntoRegion = true
        return .success(Call(action: "segment.merge", params: .merge(request)))
    }

    /// The notice after Cut Words finds words broken at a line's end, or nil when it found none.
    static func brokenWordsNotice(_ pairs: Int) -> String? {
        guard pairs > 0 else { return nil }
        return pairs == 1
            ? "1 word goes on onto the next line: Edit › Segments ▸ Join Broken Words joins it"
            : "\(pairs) words go on onto the next line: Edit › Segments ▸ Join Broken Words joins them"
    }

    /// CUT CHARACTERS in the selected words (`segment-editor.cut-characters`): one `segment.cut_characters`, one undo.
    /// The engine cuts each word at its character positions and says which words it could not cut.
    static func cutCharacters(_ segments: [Segment]) -> Result<Call, Refusal> {
        let words = segments.filter { $0.kind.lowercased() == "word" }
        guard !words.isEmpty else { return .failure(.tooFew) }
        guard let versions = versions(of: words) else { return .failure(.versionUnknown) }
        return .success(Call(
            action: "segment.cut_characters",
            params: .cutCharacters(SegmentCutWordsRequest(segmentIds: words.map(\.id), expectedVersions: versions))
        ))
    }

    /// ADD BASELINE to the selected lines that have none (`segment-editor.edge.no-baseline`): the engine proposes one
    /// through each box in its direction, marked estimated, for the person to drag onto the ink. One undo.
    static func addBaseline(_ lines: [Segment]) -> Result<Call, Refusal> {
        let wanting = lines.filter { !hasBaseline($0) }
        guard !wanting.isEmpty else { return .failure(.tooFew) }
        guard let versions = versions(of: wanting) else { return .failure(.versionUnknown) }
        return .success(Call(
            action: "segment.add_baseline",
            params: .addBaseline(SegmentCutWordsRequest(segmentIds: wanting.map(\.id), expectedVersions: versions))
        ))
    }

    /// CONVERT TO BOX (`segment-editor.convert-to-box`): each selected segment that has a polygon becomes its
    /// bounding rectangle, in one `segment.convert_to_box` and one undo. A segment that is already a box is left out.
    static func convertToBox(_ segments: [Segment]) -> Result<Call, Refusal> {
        let polygons = segments.filter { ($0.anchor.polygon?.count ?? 0) >= 3 }
        guard !polygons.isEmpty else { return .failure(.tooFew) }
        guard let versions = versions(of: polygons) else { return .failure(.versionUnknown) }
        return .success(Call(
            action: "segment.convert_to_box",
            params: .convertToBox(SegmentCutWordsRequest(segmentIds: polygons.map(\.id), expectedVersions: versions))
        ))
    }

    /// CONVERT TO LINE / CONVERT TO REGION (`segment-editor.convert-level`): each selected segment not already at the level
    /// `to` takes it, in one `segment.convert_level` and one undo. A segment already there is left out.
    static func convertLevel(_ segments: [Segment], to level: String) -> Result<Call, Refusal> {
        let changing = segments.filter { $0.kind != level }
        guard !changing.isEmpty else { return .failure(.tooFew) }
        guard let versions = versions(of: changing) else { return .failure(.versionUnknown) }
        return .success(Call(
            action: "segment.convert_level",
            params: .convertLevel(SegmentConvertLevelRequest(segmentIds: changing.map(\.id), level: level, expectedVersions: versions))
        ))
    }

    /// MAKE REGION FROM LINES (`segment-editor.make-region-from-lines`): two or more selected segments become the children
    /// of one new region, in one `segment.group_lines` and one undo.
    static func groupLines(_ lines: [Segment]) -> Result<Call, Refusal> {
        guard lines.count >= 2 else { return .failure(.tooFew) }
        guard let versions = versions(of: lines) else { return .failure(.versionUnknown) }
        return .success(Call(
            action: "segment.group_lines",
            params: .groupLines(SegmentCutWordsRequest(segmentIds: lines.map(\.id), expectedVersions: versions))
        ))
    }

    /// UNGROUP REGION: a region's lines go to its parent and the region is removed, in one `segment.ungroup_region`.
    static func ungroupRegion(_ region: Segment) -> Result<Call, Refusal> {
        guard region.kind == "region" else { return .failure(.tooFew) }
        guard let version = region.version else { return .failure(.versionUnknown) }
        return .success(Call(
            action: "segment.ungroup_region",
            params: .ungroupRegion(SegmentUngroupRegionRequest(regionId: region.id, expectedVersion: version))
        ))
    }

    /// How many points the segments' outlines and baselines hold in all.
    static func pointCount(_ segments: [Segment]) -> Int {
        segments.reduce(0) { $0 + ($1.anchor.polygon?.count ?? 0) + ($1.baseline?.count ?? 0) }
    }

    /// What Simplify says it did: how many points it took out.
    static func simplifyNotice(removed: Int) -> String {
        removed <= 0 ? "Simplify removed no points" : "Simplify removed \(removed) \(removed == 1 ? "point" : "points")"
    }

    /// What Cut Words says when it could not cut every line: how many it left, and that they need a reading or ink.
    static func cutWordsNotice(made: Int, leftAlone: Int) -> String? {
        guard leftAlone > 0 else { return nil }
        let lines = leftAlone == 1 ? "1 line" : "\(leftAlone) lines"
        return "Made \(made) words; \(lines) could not be cut (no reading, or no gaps to find)"
    }

    /// `[minX, minY, maxX, maxY]` of some points; nil for none.
    private static func bounds(of points: [[Double]]) -> [Double]? {
        let lefts = points.compactMap { $0.first }, tops = points.compactMap { $0.count > 1 ? $0[1] : nil }
        guard let minX = lefts.min(), let maxX = lefts.max(), let minY = tops.min(), let maxY = tops.max() else { return nil }
        return [minX, minY, maxX, maxY]
    }

    /// A baseline of two or more points: what Redraw and the knife need.
    static func hasBaseline(_ segment: Segment) -> Bool { (segment.baseline?.count ?? 0) >= 2 }
}

/// `segment.regenerate_outline`: Redraw Outline from Baseline. `fixedHeight` (image pixels) is for a page with no
/// ink to measure; absent, the engine measures the ink.
struct SegmentRegenerateOutlineRequest: Encodable, Equatable {
    let segmentIds: [String]
    let expectedVersions: [String: Int]
    var fixedHeight: Double?

    enum CodingKeys: String, CodingKey {
        case segmentIds = "segment_ids", expectedVersions = "expected_versions", fixedHeight = "fixed_height"
    }
}

/// `segment.split` with `cut_path`: the Knife. Every line named in `expectedVersions` whose baseline the stroke
/// crosses is cut there, in one action.
struct SegmentKnifeRequest: Encodable, Equatable {
    let cutPath: [[Double]]
    let expectedVersions: [String: Int]

    enum CodingKeys: String, CodingKey { case cutPath = "cut_path", expectedVersions = "expected_versions" }
}

/// `segment.simplify`: fewer points on each outline and baseline, within `tolerance` image pixels.
struct SegmentSimplifyRequest: Encodable, Equatable {
    let segmentIds: [String]
    let expectedVersions: [String: Int]
    let tolerance: Double

    enum CodingKeys: String, CodingKey {
        case segmentIds = "segment_ids", expectedVersions = "expected_versions", tolerance
    }
}

/// `segment.cut_words`: the lines to cut into words, with the versions read.
struct SegmentCutWordsRequest: Encodable, Equatable {
    let segmentIds: [String]
    let expectedVersions: [String: Int]

    enum CodingKeys: String, CodingKey { case segmentIds = "segment_ids", expectedVersions = "expected_versions" }
}

/// `segment.convert_level`: the segments to change, the level they take (`to_kind`: `line` or `region`), and the versions read.
struct SegmentConvertLevelRequest: Encodable, Equatable {
    let segmentIds: [String]
    let level: String
    let expectedVersions: [String: Int]

    enum CodingKeys: String, CodingKey { case segmentIds = "segment_ids", level = "to_kind", expectedVersions = "expected_versions" }
}

/// `segment.ungroup_region`: one region, at the version the caller read.
struct SegmentUngroupRegionRequest: Encodable, Equatable {
    let regionId: String
    let expectedVersion: Int
    enum CodingKeys: String, CodingKey { case regionId = "region_id", expectedVersion = "expected_version" }
}

extension SegmentEdit.Params {
    /// The tools' request bodies, the second half of `payload`, so neither switch carries every kind.
    var toolPayload: any Encodable {
        switch self {
        case .reparent(let params): params
        case .regenerateOutline(let params): params
        case .knife(let params): params
        case .simplify(let params): params
        case .cutWords(let params), .joinRows(let params): params
        case .addBaseline(let params), .cutCharacters(let params), .convertToBox(let params), .groupLines(let params): params
        case .ungroupRegion(let params): params
        case .convertLevel(let params): params
        case .sequence(let params): params
        case .moveInOrder(let params): params
        case .translate(let params): params
        case .moveCut(let params): params
        case .update, .baseline, .create, .delete, .merge, .updateMany: payload
        }
    }
}

/// `segment.translate`: the selection moved by one offset in the page's fractions (`segment-editor.group-drag`).
struct SegmentTranslateRequest: Encodable, Equatable {
    let segments: [SegmentReparentRequest.Item]
    let across: Double
    let down: Double

    enum CodingKeys: String, CodingKey { case segments, across = "dx", down = "dy" }
}

/// `segment.move_cut`: a cut mark moved along its line's baseline.
struct SegmentMoveCutRequest: Encodable, Equatable {
    let firstId: String
    let secondId: String
    let place: Double
    let expectedVersions: [String: Int]

    enum CodingKeys: String, CodingKey {
        case firstId = "first_id", secondId = "second_id", place = "at", expectedVersions = "expected_versions"
    }
}
