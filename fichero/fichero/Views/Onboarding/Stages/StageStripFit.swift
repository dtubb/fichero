import CoreGraphics
import Foundation

/// How a stage page's result strip lays its pictures out so none is hidden (`source.onboard.stages.output-visible-without-hunting`, #6402):
/// when they fit the column they share its width; when they do not, the strip says so in words and the last picture is cut at the edge.
/// A pure function of the column's width, the picture count and the readable minimum.
enum StageStripFit: Equatable {
    /// Every picture is shown whole, each this wide.
    case fits(pictureWidth: CGFloat)
    /// The pictures are each at least the minimum; the strip scrolls and says so.
    case scrolls(pictureWidth: CGFloat, cue: String)

    nonisolated static func layout(columnWidth: CGFloat, count: Int, minimum: CGFloat, spacing: CGFloat = 12) -> StageStripFit {
        let gaps = spacing * CGFloat(max(0, count - 1))
        let each = ((columnWidth - gaps) / CGFloat(max(1, count))).rounded(.down)
        if count <= 1 || each >= minimum { return .fits(pictureWidth: max(each, minimum)) }
        return .scrolls(pictureWidth: minimum, cue: cue(count: count))
    }

    /// "3 results · scroll →" (the acceptance's own text), with its plural.
    nonisolated static func cue(count: Int) -> String { "\(count) result\(count == 1 ? "" : "s") · scroll →" }

    nonisolated var cueWords: String? {
        if case .scrolls(_, let cue) = self { return cue }
        return nil
    }

    nonisolated var pictureWidth: CGFloat {
        switch self {
        case .fits(let width), .scrolls(let width, _): return width
        }
    }
}
