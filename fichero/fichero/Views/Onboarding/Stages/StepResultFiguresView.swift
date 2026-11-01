import SwiftUI

/// The figures a try adds under the output state (`wide.nomodel.tie-figures-on-his-pages`, `wide.faded.line-counts-before-and-after`):
/// the tie's counts after Read's try, and Find Lines' two counts per page with Clarity's note on a faded page. The engine counts and
/// `StepRowWords` joins the words; this lays them out. Behind the `wideSetUp` flag.
struct StepResultFiguresView: View {
    let result: SetupStageTryResult
    /// A sample page's name by id.
    let name: (String) -> String
    /// Opens the disagreement view on the first page; the button shows only when the tie left lines to look at.
    var showDifferences: (() -> Void)?

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            if let tie = result.tieWords {
                Text(tie).font(.callout).accessibilityIdentifier("setup.output.tie")
                if let showDifferences, StepRowWords.offersUntied(result.tie?.counts) {
                    Button("See where they differ", action: showDifferences)
                        .accessibilityIdentifier("setup.step.noModel.read-a-line.showUntied")
                }
            }
            if let both = result.lineCounts?.pages {
                ForEach(both.keys.sorted(), id: \.self) { page in
                    if let counts = both[page] {
                        Text("\(name(page)): \(StepRowWords.lineCounts(counts))").font(.callout)
                            .accessibilityIdentifier("setup.findLines.clarifiedCount")
                    }
                }
            }
            if let faded = result.lineCounts?.notClarified, !faded.isEmpty {
                Text(StepRowWords.clarityOff).font(.caption).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }
}

#Preview("Tie figures and line counts") {
    let json = #"{"state":"done","tie":{"counts":{"tied":9,"doubtful":2,"untied":1,"drafts":1}}}"#
    if let result = try? JSONDecoder().decode(SetupStageTryResult.self, from: Data(json.utf8)) {
        StepResultFiguresView(result: result, name: { $0 }, showDifferences: {}).padding().frame(width: 420)
    }
}
