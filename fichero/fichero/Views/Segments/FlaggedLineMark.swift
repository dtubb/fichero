import SwiftUI

/// The small mark on a line the teacher-line check flagged (#5446), wherever lines are listed: the
/// Segments pane's list, strip and grid, and the Order list. Hovering says the flag and its scores in
/// words; the Inspector says them too, with Confirm.
struct FlaggedLineMark: View {
    let line: FlaggedLines.Line

    var body: some View {
        Image(systemName: "flag.fill")
            .font(.caption)
            .foregroundStyle(.orange)
            .help("\(line.title): \(line.words)")
            .accessibilityLabel("Flagged: \(line.title)")
            .accessibilityHint(line.words)
    }
}

/// The Inspector's word on a flagged line: the flag, its scores in words, the run's counts, and Confirm.
struct InspectorFlaggedSection: View {
    let line: FlaggedLines.Line
    /// The run's counts in words; nil when the run is not read.
    var runWords: String?
    /// Why the last Confirm did not land.
    var note: String?
    /// The person's Confirm; nil shows no verb (a preview).
    var confirm: (() -> Void)?

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Label("Flagged: \(line.title)", systemImage: "flag.fill")
                .font(.headline)
                .foregroundStyle(.orange)
            Text(line.words).font(.body)
            Text("Kept out of training sets until a person confirms the reading.")
                .font(.caption).foregroundStyle(.secondary)
            if let runWords {
                Text("The check: \(runWords).").font(.caption).foregroundStyle(.secondary)
            }
            if let confirm {
                Button("Confirm Reading", action: confirm)
                    .help("Say the reading is right: the line is no longer flagged and may teach again")
            }
            if let note {
                Text(note).font(.caption).foregroundStyle(.secondary)
            }
        }
        .accessibilityElement(children: .contain)
    }
}

#if DEBUG
private let previewNeighbour = FlaggedLines.Line(
    segmentId: "l2", readingId: "r2", runId: "run1", flag: FlaggedLines.closerToANeighbour,
    own: 0.21, neighbour: 0.52, offset: 1, low: 0.30
)

#Preview("Flagged line mark in a row") {
    HStack {
        Text("Line · dixo que el dicho")
        Spacer()
        FlaggedLineMark(line: previewNeighbour)
    }
    .padding()
    .frame(width: 320)
}

#Preview("Inspector: a line closer to the next one") {
    InspectorFlaggedSection(
        line: previewNeighbour, runWords: "40 passed, 1 closer to a neighbour, 2 below the threshold", confirm: {}
    )
    .padding()
    .frame(width: 320)
}
#endif
