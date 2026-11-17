import SwiftUI

/// Recipes' Visual view (`activity.window.centre-views`, `activity.window.recipes`, decisions 37 and 39, #6588): a run
/// drawn as its steps, node after node in the order they ran, each with its counts, so "what recipes worked" reads at a
/// glance. Drawn from the Recipes answer the outline reads; the node editor's own canvas needs the run's stored
/// workflow, which that answer does not carry.
enum ActivityRunGraph {
    struct Node: Identifiable, Equatable {
        let id: String
        let name: String
        let model: String?
        let done: Int
        let failed: Int
        let perPage: String

        /// A step that failed pages is drawn red, one that read pages green, one that read none secondary.
        var tone: Tone { failed > 0 ? .failed : (done > 0 ? .done : .none) }

        enum Tone: Equatable { case done, failed, none }
    }

    struct Run: Identifiable, Equatable {
        let id: String
        let recipe: String
        let when: Date?
        let nodes: [Node]
    }

    /// Each recipe's newest run, its steps as nodes in the order they ran; a run with no steps is left out.
    static func newestRuns(_ lines: [ActivityRecipeLine]) -> [Run] {
        lines.compactMap { recipe in
            guard let run = recipe.children?.first, let steps = run.children, !steps.isEmpty else { return nil }
            return Run(id: run.id, recipe: recipe.name, when: run.when, nodes: steps.map {
                Node(id: $0.id, name: $0.name, model: $0.model, done: $0.pagesDone, failed: $0.pagesFailed,
                     perPage: $0.perPageWords)
            })
        }
    }
}

/// The run graphs: one row per recipe, its newest run's steps as cards joined by arrows.
struct ActivityRunGraphView: View {
    let runs: [ActivityRunGraph.Run]

    var body: some View {
        if runs.isEmpty {
            Text("No recipe run has steps to draw").foregroundStyle(.secondary)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else {
            ScrollView([.vertical, .horizontal]) {
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
            .accessibilityIdentifier("activity.recipes.visual")
        }
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
