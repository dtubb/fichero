import FicheroAPIClient
import SwiftUI

extension ISO8601DateFormatter {
    /// The engine's timestamps carry fractional seconds.
    nonisolated(unsafe) static let withFractions: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter
    }()
}

/// The Recipes view's centre: an outline table, recipe › run › step, every open project's recipes read from the engine.
struct ActivityRecipesView: View {
    let libraries: [LibraryManager.LibraryReference]
    /// The Visual view: each recipe's newest run drawn as its steps (`ActivityRunGraph`), not the outline.
    var visual = false
    @State private var lines: [ActivityRecipeLine] = []
    @State private var selection: ActivityRecipeLine.ID?
    @State private var readOnce = false

    var body: some View {
        Group {
            if lines.isEmpty {
                Text(readOnce ? "No recipe has run in the last 30 days" : "Reading the recipes…")
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if visual {
                ActivityRunGraphView(runs: ActivityRunGraph.newestRuns(lines))
            } else {
                Table(lines, children: \.children, selection: $selection) {
                    TableColumn("Recipe") { line in
                        Text(line.name).fontWeight(line.level == .recipe ? .semibold : .regular)
                    }
                    .width(min: 160, ideal: 240)
                    TableColumn("Runs") { line in Text(line.runs.map(String.init) ?? "").monospacedDigit() }
                        .width(44)
                    TableColumn("Model") { line in Text(line.model ?? "").foregroundStyle(.secondary) }
                        .width(min: 80, ideal: 140)
                    TableColumn("Pages") { line in Text("\(line.pagesDone)").monospacedDigit() }
                        .width(56)
                    TableColumn("Failed") { line in
                        Text(line.pagesFailed > 0 ? "\(line.pagesFailed)" : "")
                            .foregroundStyle(.red).monospacedDigit()
                    }
                    .width(52)
                    TableColumn("Failed %") { line in Text(line.failedWords).monospacedDigit() }
                        .width(64)
                    TableColumn("A Page") { line in Text(line.perPageWords).monospacedDigit() }
                        .width(64)
                    TableColumn("Cost a Page") { line in Text(line.costWords).monospacedDigit() }
                        .width(78)
                    TableColumn("When") { line in
                        Text(line.when.map { $0.formatted(date: .abbreviated, time: .shortened) } ?? "")
                            .foregroundStyle(.secondary)
                    }
                    .width(min: 100, ideal: 140)
                }
                .accessibilityIdentifier("activity.recipes")
            }
        }
        .task(id: libraries.map(\.id)) { await read() }
    }

    private func read() async {
        var all: [Components.Schemas.RecipeRow] = []
        for library in libraries {
            if let recipes = try? await library.activityService.recipes() { all += recipes }
        }
        lines = ActivityRecipeLine.lines(all)
        readOnce = true
    }
}

#Preview("Recipes") {
    ActivityRecipesView(libraries: [])
        .frame(width: 900, height: 300)
}
