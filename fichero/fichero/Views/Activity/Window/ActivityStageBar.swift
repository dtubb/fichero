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
        /// One red tick per failed page (the bar draws at most `maxTicks`).
        let failedPages: Int
        /// The stage's state in words, for VoiceOver: "Read, partial, 3 failed".
        let label: String
    }

    nonisolated static let maxTicks = 5

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
            let hatched = card.state == .partial || (ended && card.pagesFailed > 0)
            let words = [card.title, hatched ? "partial" : card.stateWords.lowercased(),
                         card.pagesFailed > 0 ? "\(card.pagesFailed) failed" : nil].compactMap { $0 }
            return Segment(id: card.id, title: card.title, fill: fill, hatched: hatched,
                           failedPages: card.pagesFailed, label: words.joined(separator: ", "))
        }
    }

    /// The stores' trees by library; two stores with one id keep the first, never a crash.
    nonisolated static func trees(_ stores: [(UUID, [String: ActivityJobNode])]) -> [UUID: [String: ActivityJobNode]] {
        Dictionary(stores, uniquingKeysWith: { first, _ in first })
    }

    /// Where the failed-page ticks sit, as fractions of the segment's width: along the filled part, or across the
    /// whole segment when nothing is filled (a stage that failed before it counted a page).
    nonisolated static func tickPositions(count: Int, fill: Double) -> [Double] {
        let ticks = min(count, maxTicks)
        let span = fill > 0 ? fill : 1
        return (0..<ticks).map { span * Double($0 + 1) / Double(ticks + 1) }
    }

    /// The row's bar, from the tree in the store of the row's OWN library (`trees`, by library), so every project's
    /// recipe row has one.
    nonisolated static func segments(for row: ActivityMonitorRow,
                                     trees: [UUID: [String: ActivityJobNode]]) -> [Segment] {
        guard let library = row.libraryId, let thread = row.runThreadId else { return [] }
        return segments(of: ActivityDetails.stageCards(of: trees[library]?[thread]))
    }

    var body: some View {
        HStack(spacing: 2) {
            ForEach(segments) { segment in
                GeometryReader { proxy in
                    let width = proxy.size.width
                    ZStack(alignment: .leading) {
                        Capsule().fill(.quaternary)
                        Capsule().fill(.tint).frame(width: width * segment.fill)
                        if segment.hatched {
                            Hatch().stroke(.white.opacity(0.6), lineWidth: 1.5)
                                .frame(width: width * segment.fill)
                                .clipShape(Capsule())
                        }
                        // ticks sit by position across the filled part, one per failed page
                        let ticks = Self.tickPositions(count: segment.failedPages, fill: segment.fill)
                        ForEach(Array(ticks.enumerated()), id: \.offset) { _, position in
                            Rectangle().fill(.red).frame(width: 2).frame(maxHeight: .infinity)
                                .offset(x: max(0, width * position - 1))
                        }
                    }
                }
                .frame(height: 6)
                .help(segment.label)
                .accessibilityElement()
                .accessibilityLabel(segment.label)
                .accessibilityIdentifier("activity.window.stageBar.\(segment.id)")
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("activity.window.stageBar")
    }
}

/// Diagonal stripes, the hatch of a partial segment.
private struct Hatch: Shape {
    func path(in rect: CGRect) -> Path {
        var path = Path()
        var x = -rect.height
        while x < rect.width {
            path.move(to: CGPoint(x: x, y: rect.height))
            path.addLine(to: CGPoint(x: x + rect.height, y: 0))
            x += 4
        }
        return path
    }
}

#Preview("A run part-way") {
    ActivityStageBar(segments: [
        .init(id: "find-lines", title: "Find Lines", fill: 1, hatched: false, failedPages: 0, label: "Find Lines, done"),
        .init(id: "read", title: "Read", fill: 0.4, hatched: true, failedPages: 2, label: "Read, partial, 2 failed"),
        .init(id: "names", title: "Names", fill: 0, hatched: false, failedPages: 0, label: "Names, waiting"),
    ])
    .frame(width: 320)
    .padding()
}
