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
    /// fractions), with the versions of every line whose box it reaches. The engine decides which it crosses: a
    /// line it only grazes is left alone and named in the answer. Lines with no baseline or no version are not
    /// offered; a stroke that reaches no line, or a click with no length, sends nothing.
    static func knife(_ stroke: [[Double]], over lines: [Segment]) -> Result<Call, Refusal> {
        guard stroke.count >= 2, let reach = bounds(of: stroke) else { return .failure(.tooFew) }
        let reached = lines.filter { line in
            guard hasBaseline(line), let rect = line.anchor.rect, rect.count >= 4 else { return false }
            return rect[0] <= reach[2] && reach[0] <= rect[0] + rect[2] && rect[1] <= reach[3] && reach[1] <= rect[1] + rect[3]
        }
        guard !reached.isEmpty else { return .failure(.tooFew) }
        let versioned = reached.filter { $0.version != nil }
        guard !versioned.isEmpty, let versions = versions(of: versioned) else { return .failure(.versionUnknown) }
        return .success(Call(
            action: "segment.split",
            params: .knife(SegmentKnifeRequest(cutPath: stroke, expectedVersions: versions))
        ))
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
