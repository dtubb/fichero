import Foundation

extension ActivityStore {
    /// The engine's job kind for a Find the Documents run, from the menu or as a recipe's step (`finddocs/job.KIND`).
    static let findDocumentsKind = "find-documents-in-a-folder"

    /// Whether a Find the Documents run that was under way in one jobs read has ended by the next: it left the list
    /// (a finished job is not listed), or it is listed as done or failed (`finddocs.review.items`).
    static func aFindDocumentsRunEnded(from before: [ActivityJob], to after: [ActivityJob]) -> Bool {
        let now = Dictionary(after.map { ($0.id, $0.state) }, uniquingKeysWith: { first, _ in first })
        return before.contains { job in
            guard job.taskType == findDocumentsKind, !hasEnded(job.state) else { return false }
            return now[job.id].map(hasEnded) ?? true
        }
    }

    private static func hasEnded(_ state: ActivityJob.State) -> Bool {
        state == .completed || state == .failed
    }
}
