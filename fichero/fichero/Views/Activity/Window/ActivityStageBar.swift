import SwiftUI

/// The one segmented bar on a recipe run's row (`activity.window.stage-bar`, #5960): the run's stages in Set Up's
/// order, a segment filling by pages done. A stage that has ended is full whatever its counts now say, so the row never
/// looks as if it went back (#5871). A red tick is a failed page; a hatched segment is partial; an empty one waits.
struct ActivityStageBar: View {
    struct Segment: Equatable, Identifiable {
        let id: String
        let title: String
        /// 0...1.
        let fill: Double
        let hatched: Bool
        /// One red tick per failed page.
        let failedPages: Int
    }

    let segments: [Segment]

    /// A segment per stage the run ran; a stage the plan skipped has no segment.
    nonisolated static func segments(of cards: [ActivityDetails.StageCard]) -> [Segment] {
        cards.filter { $0.state != .skipped }.map { card in
            let counted = card.total > 0 ? min(1, Double(card.done) / Double(card.total)) : 0
            let fill: Double = switch card.state {
            case .done, .partial: 1  // ended: full, even when its count moves or it has none
            case .running, .failed: counted
            case .waiting, .notRun, .unknown, .skipped: 0
            }
            // an ended stage with failed pages is full AND hatched, like a partial one
            let ended = card.state == .done || card.state == .partial
            return Segment(id: card.id, title: card.title, fill: fill,
                           hatched: card.state == .partial || (ended && card.pagesFailed > 0),
                           failedPages: card.pagesFailed)
        }
    }

    var body: some View {
        HStack(spacing: 2) {
            ForEach(segments) { segment in
                GeometryReader { proxy in
                    ZStack(alignment: .leading) {
                        Capsule().fill(.quaternary)
                        Capsule()
                            .fill(segment.hatched ? AnyShapeStyle(.orange.opacity(0.6)) : AnyShapeStyle(.tint))
                            .frame(width: proxy.size.width * segment.fill)
                        ForEach(0..<min(segment.failedPages, 5), id: \.self) { index in
                            Rectangle().fill(.red).frame(width: 2).frame(maxHeight: .infinity)
                                .offset(x: max(0, proxy.size.width * segment.fill - 2 - CGFloat(index) * 4))
                        }
                    }
                }
                .frame(height: 6)
                .help(segment.title)
                .accessibilityIdentifier("activity.window.stageBar.\(segment.id)")
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("activity.window.stageBar")
    }
}

#Preview("A run part-way") {
    ActivityStageBar(segments: [
        .init(id: "find-lines", title: "Find Lines", fill: 1, hatched: false, failedPages: 0),
        .init(id: "read", title: "Read", fill: 0.4, hatched: false, failedPages: 2),
        .init(id: "names", title: "Names", fill: 0, hatched: false, failedPages: 0),
    ])
    .frame(width: 320)
    .padding()
}
