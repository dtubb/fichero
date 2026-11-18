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
        var tone: ActivityRunGraphTone { failed > 0 ? .failed : (done > 0 ? .done : .none) }
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
