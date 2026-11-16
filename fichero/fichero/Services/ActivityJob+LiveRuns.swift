import FicheroAPIClient
import Foundation

/// The window reads live recipe runs from the engine's live blocks (`activity.summary.one-row-per-run-in-list`, #5960): the engine lists a
/// run that is a live block once, as a block, and not also as a `jobs` row. Every surface of the app is built on `ActivityJob` rows, so
/// each live block that names a recipe is turned into the one row it was, here, in the one place the snapshot is read. A run the list
/// still names (an old engine, or a history row) is not added twice.
extension ActivityJob {
    static let recipeRunKind = "run-a-recipe"

    /// The row for one live recipe block: the run's name and state, its running stage's pages as its bar.
    init(liveBlock block: Components.Schemas.LiveBlock) {
        let count = block.total ?? 0
        let done = block.done ?? 0
        self.init(
            id: block.id, taskType: Self.recipeRunKind, name: block.recipe ?? block.id,
            current: done, total: count,
            percent: count > 0 ? (Double(done) * 100 / Double(count)).rounded(toPlaces: 1) : 0,
            state: State(raw: block.state), reason: block.reason)
    }

    /// `jobs` with each live recipe block that is not already a row put first, as live rows are listed.
    static func withLiveRuns(_ jobs: [ActivityJob], live: [Components.Schemas.LiveBlock]) -> [ActivityJob] {
        let listed = Set(jobs.map(\.id))
        let added = live.filter { $0.recipe != nil && !listed.contains($0.id) }.map { ActivityJob(liveBlock: $0) }
        return added + jobs
    }
}

private extension Double {
    func rounded(toPlaces places: Int) -> Double {
        let scale = Foundation.pow(10.0, Double(places))
        return (self * scale).rounded() / scale
    }
}
