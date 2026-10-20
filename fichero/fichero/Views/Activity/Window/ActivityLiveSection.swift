import FicheroAPIClient
import SwiftUI

/// The top of the Activity window (`activity.window.live-block`, `activity.window.background-group`, #5851): one block
/// per live run, "Recipe › Stage › Workflow" over "7 of 20 pages · 2 of 8 folders", then one line per kind of
/// background work with its total. It reads the engine's summary through the popover's own mapping
/// (`ActivityPopoverSummary.block`), so the window and the popover always agree (`activity.popover.same-summary`).
/// Empty when nothing is working: the table below is all there is.
struct ActivityLiveSection: View {
    let summaries: [Components.Schemas.ActivitySummary]

    var blocks: [ActivityPopoverSummary.Block] {
        summaries.flatMap { $0.live ?? [] }.map(ActivityPopoverSummary.block)
    }

    var background: [ActivityPopoverSummary.BackgroundRow] {
        summaries.flatMap { $0.background ?? [] }.map(ActivityPopoverSummary.backgroundLine)
    }

    var body: some View {
        if !blocks.isEmpty || !background.isEmpty {
            VStack(alignment: .leading, spacing: 8) {
                ForEach(blocks) { block in
                    ActivityPopoverBlockView(block: block)
                }
                if !background.isEmpty {
                    Divider()
                    ForEach(background) { line in
                        Label(line.waiting.map { "\(line.text) · \($0)" } ?? line.text,
                              systemImage: line.waiting == nil ? "arrow.triangle.2.circlepath" : "clock")
                            .font(.callout)
                            .foregroundStyle(line.waiting == nil ? AnyShapeStyle(.primary) : AnyShapeStyle(.secondary))
                            .accessibilityIdentifier("activity.window.background")
                    }
                }
            }
            .padding(12)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(.bar)
            .accessibilityIdentifier("activity.window.live")
            Divider()
        }
    }
}

#Preview("A live run and background work") {
    let json = """
    [{"live":[{"id":"r1","recipe":"Transcribe the Mosquera box","stage":"Reading lines","workflow":"Kraken","state":"running",
               "done":36,"failed":1,"left":55,"total":92,"folders_done":2,"folders_total":8}],
      "background":[{"kind":"embed","name":"Embedding pages","state":"running","done":42,"total":100},
                    {"kind":"thumbnails","name":"Thumbnails","state":"waiting","reason":"Waiting: memory is tight","total":12}],
      "history":3}]
    """
    let summaries = (try? JSONDecoder().decode([Components.Schemas.ActivitySummary].self, from: Data(json.utf8))) ?? []
    ActivityLiveSection(summaries: summaries)
        .frame(width: 520)
}
