import SwiftUI

/// A Segments row's facts, after its words (`source.editor.segment-row-shows-its-facts-as-icons`, Step 1.28, first
/// slice): its count, a direction arrow, language and script capsules (dimmed when inherited, the tooltip naming where
/// from), and its reading's state (a person's, doubtful with its confidence, or none yet). The facts are
/// `SegmentRowFacts`; which ones show is the pane's "Show in Rows" choice.
struct SegmentRowFactsView: View {
    let facts: SegmentRowFacts
    let shown: Set<SegmentRowFacts.Shown>
    /// Names the segment a value was inherited from ("its region"), for the tooltip.
    var source: (String) -> String = { _ in "a parent segment" }

    var body: some View {
        HStack(spacing: 4) {
            if shown.contains(.count), let count = facts.count {
                Text(count.short)
                    .font(.caption2)
                    .monospacedDigit()
                    .foregroundStyle(.secondary)
                    .help(count.words)
            }
            if shown.contains(.direction), let direction = facts.direction {
                Image(systemName: Self.arrow(direction.value))
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .opacity(direction.inherited ? 0.5 : 1)
                    .help(Self.tooltip("Direction \(direction.value)", direction, source))
                    .accessibilityLabel("Direction \(direction.value)")
            }
            if shown.contains(.language), let language = facts.language {
                capsule(language, label: "Language")
            }
            if shown.contains(.script), let script = facts.script {
                capsule(script, label: "Script")
            }
            if shown.contains(.reading) {
                readingMark
            }
        }
    }

    private func capsule(_ stated: SegmentRowFacts.Stated, label: String) -> some View {
        Text(stated.value)
            .font(.caption2)
            .foregroundStyle(.secondary)
            .padding(.horizontal, 4)
            .background(Capsule().strokeBorder(.secondary.opacity(0.5)))
            .opacity(stated.inherited ? 0.5 : 1)
            .help(Self.tooltip("\(label) \(stated.value)", stated, source))
            .accessibilityLabel("\(label) \(stated.value)")
    }

    @ViewBuilder private var readingMark: some View {
        switch facts.reading {
        case .person:
            Image(systemName: "person.fill")
                .font(.caption2)
                .foregroundStyle(.secondary)
                .help("A person's reading")
                .accessibilityLabel("A person's reading")
        case .doubtful(let confidence):
            Label(Self.percent(confidence), systemImage: "exclamationmark.triangle.fill")
                .labelStyle(.titleAndIcon)
                .font(.caption2)
                .foregroundStyle(.orange)
                .help("A machine's reading, doubtful: \(Self.percent(confidence)) confident")
        case .none:
            Text("no reading")
                .font(.caption2)
                .foregroundStyle(.tertiary)
        case .machine, .notRead:
            EmptyView()
        }
    }

    /// The arrow a writing direction reads in: left to right, right to left, top to bottom, bottom to top.
    nonisolated static func arrow(_ direction: String) -> String {
        switch direction.lowercased() {
        case "rtl": "arrow.left"
        case "ttb": "arrow.down"
        case "btt": "arrow.up"
        default: "arrow.right"
        }
    }

    /// "Language es" for its own value; "Language es, from its region" for an inherited one.
    nonisolated static func tooltip(_ what: String, _ stated: SegmentRowFacts.Stated, _ source: (String) -> String) -> String {
        guard let from = stated.fromSegmentId else { return what }
        return "\(what), from \(source(from))"
    }

    nonisolated static func percent(_ confidence: Double) -> String { "\(Int((confidence * 100).rounded()))%" }
}

#Preview("Segment row facts: own and inherited, doubtful and a person's") {
    VStack(alignment: .leading, spacing: 8) {
        SegmentRowFactsView(
            facts: SegmentRowFacts(
                count: .lines(3), direction: .init(value: "ltr", fromSegmentId: nil),
                language: .init(value: "es", fromSegmentId: nil), script: .init(value: "Latn", fromSegmentId: nil),
                reading: .notRead
            ),
            shown: Set(SegmentRowFacts.Shown.allCases)
        )
        SegmentRowFactsView(
            facts: SegmentRowFacts(
                count: .words(4), direction: .init(value: "ltr", fromSegmentId: "r1"),
                language: .init(value: "es", fromSegmentId: "r1"), script: nil, reading: .doubtful(0.42)
            ),
            shown: Set(SegmentRowFacts.Shown.allCases), source: { _ in "its region" }
        )
        SegmentRowFactsView(
            facts: SegmentRowFacts(count: .words(6), direction: nil, language: nil, script: nil, reading: .person),
            shown: Set(SegmentRowFacts.Shown.allCases)
        )
    }
    .padding()
}
