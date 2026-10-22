import SwiftUI

/// The run's pages as dots (`activity.window.page-grid`, #5960): done, running, waiting, failed; hovering says the page and,
/// for a failed or waiting one, why; clicking opens the page. It does not yet replace the page rows and the list of queued
/// pages (`activity.window.page-grid`, [PARTIAL]); they are still shown beside it.
struct ActivityPageGridView: View {
    let grid: ActivityPageGrid
    let open: (String) -> Void
    /// Select the pages this grid shows (the run's pages, at most the 2,000 it reads) in the project ("Show the run's pages…"):
    /// done pages are reachable without a pointer.
    var showAll: ([String]) -> Void = { _ in }

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 10, maximum: 10), spacing: 3)], alignment: .leading, spacing: 3) {
                ForEach(grid.pages) { page in
                    Circle()
                        .fill(Self.color(page.dot))
                        .frame(width: 10, height: 10)
                        .help(page.help)
                        .onTapGesture { open(page.id) }
                }
            }
            if grid.notShown > 0 {
                Text("and \(grid.notShown) more").font(.caption).foregroundStyle(.secondary)
            }
        }
        // One stop for the whole grid, not one per dot (up to 2,000), with an Open action for each page that needs a look
        // ("Open p12.jpg, failed"), the failed ones first; a click opens any dot.
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(grid.summary)
        .accessibilityActions {
            ForEach(grid.actionPages) { page in
                Button("Open \(page.accessibilityLabel)") { open(page.id) }
            }
            Button(ActivityPageGrid.showAllTitle) { showAll(grid.pages.map(\.id)) }
        }
        .accessibilityIdentifier("activity.details.pageGrid")
    }

    static func color(_ dot: ActivityPageGrid.Dot) -> Color {
        switch dot {
        case .done: .green
        case .running: .blue
        case .waiting: .gray.opacity(0.5)
        case .unknown: .gray
        case .failed: .red
        }
    }
}
