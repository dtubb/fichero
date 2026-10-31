import FicheroAPIClient
import Foundation

/// The Prepare Images page's operation rows (`wide.prepare.four-operations-listed`, #5580): one switch per operation, in the
/// engine's order, each with its sentence. The engine says which are on by the questions' defaults; the person's hand is the one
/// answer `prepare_operations` (a list of the operations that are on), and it wins over the defaults. Pure: no view, no network.
struct PrepareOperationRow: Equatable, Identifiable {
    let id: String
    let title: String
    let sentence: String
    let note: String?
    var isOn: Bool
}

enum PrepareOperationRows {
    /// The answer's key in `answers.job_answers` (`recipes/prepare_operations.py`).
    static let question = "prepare_operations"

    /// The rows: the listing's operations in its order. With the person's answer, a row is on when the answer holds it; without
    /// one, the engine's own `on` stands.
    static func rows(of operations: [Components.Schemas.PrepareOperation], answer: StageAnswer?) -> [PrepareOperationRow] {
        let chosen: Set<String>? = if case .many(let ids)? = answer { Set(ids) } else { nil }
        return operations.map { op in
            PrepareOperationRow(id: op.id.rawValue, title: op.title, sentence: op.sentence, note: op.note,
                                isOn: chosen.map { $0.contains(op.id.rawValue) } ?? op.on)
        }
    }

    /// The answer after the person switches `id`: every row's state as shown, with that one changed, in the engine's order, so
    /// a first switch also keeps the others as they were (the answer is the whole list, never one change).
    static func answer(after switching: String, to on: Bool, rows: [PrepareOperationRow]) -> StageAnswer {
        .many(rows.filter { $0.id == switching ? on : $0.isOn }.map(\.id))
    }

    /// The one line the page says when operations are off: nothing to prepare when every one is off.
    static func summary(of rows: [PrepareOperationRow]) -> String {
        let on = rows.filter(\.isOn)
        if on.isEmpty { return "Every operation is off: Prepare Images runs nothing." }
        return "Runs: " + on.map { $0.title.lowercased() }.joined(separator: ", ") + "."
    }
}

extension RecipeSetupStore {
    /// The rows for the Prepare Images page, from the stage listing and the person's answer.
    var prepareOperationRows: [PrepareOperationRow] {
        let operations = stage("prepare-images")?.operations ?? []
        return PrepareOperationRows.rows(of: operations, answer: jobAnswers[question: PrepareOperationRows.question])
    }

    /// Switch one operation: the whole list is saved as the answer, so the engine's plan follows it.
    func setPrepareOperation(_ id: String, on: Bool) {
        let rows = prepareOperationRows
        guard rows.contains(where: { $0.id == id }) else { return }
        jobAnswers[question: PrepareOperationRows.question] = PrepareOperationRows.answer(after: id, to: on, rows: rows)
    }
}
