import SwiftUI

/// The run graphs: one row per recipe, its newest run's steps as cards joined by arrows.
struct ActivityRunGraphView: View {
    let runs: [ActivityRunGraph.Run]

    var body: some View {
        if runs.isEmpty {
            Text("No recipe run has steps to draw").foregroundStyle(.secondary)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else {
            ScrollView([.vertical, .horizontal]) { runList }
                .accessibilityIdentifier("activity.recipes.visual")
        }
    }

    private var runList: some View {
        VStack(alignment: .leading, spacing: 18) {
            ForEach(runs) { run in
                VStack(alignment: .leading, spacing: 6) {
                    Text(run.recipe).font(.headline)
                        + Text(run.when.map { "  \($0.formatted(date: .abbreviated, time: .shortened))" } ?? "")
                        .font(.caption).foregroundColor(.secondary)
                    HStack(spacing: 6) {
                        ForEach(Array(run.nodes.enumerated()), id: \.element.id) { index, node in
                            if index > 0 {
                                Image(systemName: "arrow.right").foregroundStyle(.tertiary)
                                    .accessibilityHidden(true)
                            }
                            nodeCard(node)
                        }
                    }
                }
            }
        }
        .padding(12)
    }

    private func nodeCard(_ node: ActivityRunGraph.Node) -> some View {
        let tint: Color = switch node.tone {
        case .failed: .red
        case .done: .green
        case .none: .secondary
        }
        return VStack(alignment: .leading, spacing: 2) {
            Text(node.name).font(.callout.weight(.semibold)).lineLimit(1)
            if let model = node.model { Text(model).font(.caption).foregroundStyle(.secondary).lineLimit(1) }
            HStack(spacing: 6) {
                Text("\(node.done) done").monospacedDigit()
                if node.failed > 0 { Text("\(node.failed) failed").foregroundStyle(.red).monospacedDigit() }
                if !node.perPage.isEmpty { Text("\(node.perPage) a page").foregroundStyle(.secondary) }
            }
            .font(.caption)
        }
        .padding(8)
        .frame(minWidth: 120, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: 6).fill(tint.opacity(0.08)))
        .overlay(RoundedRectangle(cornerRadius: 6).strokeBorder(tint.opacity(0.5)))
        .accessibilityElement(children: .combine)
    }
}

#Preview("Run graph") {
    func step(_ id: String, _ name: String, done: Int, failed: Int = 0, model: String? = nil) -> ActivityRecipeLine {
        ActivityRecipeLine(id: id, level: .step, name: name, model: model, pagesDone: done, pagesFailed: failed,
                           secondsPerPage: 4, children: nil)
    }
    let run = ActivityRecipeLine(
        id: "run:1", level: .run, name: "Done",
        children: [step("s1", "Detect Segments", done: 20, model: "kraken:blla"),
                   step("s2", "Read Lines", done: 17, failed: 3, model: "kraken:catmus")])
    let recipe = ActivityRecipeLine(
        id: "recipe:a", level: .recipe, name: "Letters",
        children: [run])
    return ActivityRunGraphView(runs: ActivityRunGraph.newestRuns([recipe])).frame(width: 480, height: 200)
}
