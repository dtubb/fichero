import Foundation

// What a finished workflow run made (`activity.window.what-it-made`): the list of its artifacts. A recipe run says it in
// its summary (`ActivityDetails+Recipe.swift`).

extension ActivityDetails {
    /// One artifact a workflow run made: what it is called (its step, else its type), its type, the document it is on.
    struct MadeItem: Equatable, Identifiable {
        let id: String
        let name: String
        let type: String
        let documentId: String
    }

    /// What a finished workflow run made (`activity.window.what-it-made`): the first few, and how many more there are.
    struct Made: Equatable {
        let items: [MadeItem]
        let more: Int
    }

    /// How many of a run's artifacts the details list before "and N more".
    static let madeShown = 50

    /// Whether the row is a workflow run that has ended: what it made is read from its artifacts. A recipe run says it in
    /// its summary.
    var madeIsRead: Bool {
        row.kind == .run && row.runThreadId != nil && node?.kind != ActivityStore.recipeRunKind
            && [.done, .partial, .failed, .cancelled, .interrupted].contains(row.phase)
    }

    static func made(row: ActivityMonitorRow, node: ActivityJobNode?, page: ArtifactService.ArtifactPage?) -> Made? {
        guard row.kind == .run, node?.kind != ActivityStore.recipeRunKind, let page, !page.items.isEmpty else { return nil }
        let items = page.items.map {
            MadeItem(id: $0.id, name: $0.stepName ?? $0.artifactType, type: $0.artifactType, documentId: $0.documentId)
        }
        return Made(items: items, more: max(0, page.count - items.count))
    }

}
