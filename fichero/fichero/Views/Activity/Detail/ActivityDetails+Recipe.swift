import FicheroAPIClient
import Foundation

// A recipe run's details (#5576, #5577; `source.onboard.auto.lands-on-the-run`,
// `source.onboard.auto.results-summary`): its stages in order and, once it has
// ended, what it made. Worded from the run's node of the job tree, the record
// the Activity table reads (`activity.details.one-record`); nothing is counted
// here.

extension ActivityDetails {
    /// One stage of a recipe run, in words.
    struct Stage: Equatable, Identifiable {
        let id: String
        /// The stage's workflow by name ("Transcribe (Kraken)"), else what the card does.
        let title: String
        /// The recipe steps it carries out: "Steps lines, read".
        let steps: String
        /// "Running", "Done", "Waiting for the stage before it", "Failed: …", "Not run: …".
        let state: String
        let isFailed: Bool
        /// "40 done · 2 failed · 158 left", from the stage's run account.
        let counts: String?
        /// "About 12m left", at the stage's own pace.
        let timeLeft: String?
        /// What its pages wait for ("memory is tight"), while it runs.
        let waitingFor: String?
        /// Why it runs on fewer pages than the project has: Start's count of what was already done (#6091).
        let note: String?
    }

    /// What a recipe run made, in words (#5577).
    struct Summary: Equatable {
        /// A stage's failed pages and its Read Again.
        struct Failed: Equatable, Identifiable {
            let id: String
            let text: String
            let offer: String?
            let threadId: String
        }

        /// A step the plan skipped, why, and whether setup has a fix for it.
        struct Skipped: Equatable, Identifiable {
            let id: String
            let text: String
            let hasFix: Bool
        }

        /// The summary in the engine's words, one line per figure, shown as given (#5577):
        /// "Read 198 of 203 pages"; "Names: 120 People · 40 Places". Empty when the engine sends none.
        let lines: [String]
        let failed: [Failed]
        let skipped: [Skipped]
        /// A step waiting on a model download that failed (#5352).
        var downloadFailed: [DownloadFailure] = []
        /// What the run did not finish and its one action (#6170, `source.recipe.run-again-on-what-was-missed`).
        var missed: MissedOffer?
    }

    /// The engine's words for what a run missed, its offer, and the run's scope; Start on that scope runs only what is
    /// not done (`source.recipe.done-is-not-redone`). The engine decides; the app only shows it.
    struct MissedOffer: Equatable {
        let words: String
        /// The action's label; nil, no action.
        let offer: String?
        /// The run's folder; nil, the project.
        let folderId: String?
        /// The run's pages when it covered some alone (a run an import started); nil, the scope is `folderId` (#6170).
        var documents: [String]?
    }

    /// A step waiting on a failed download: Retry the download's job, or take the step's next candidate (#5352,
    /// `source.recipe.download-failure-waits`). Read from the run summary's `download_failed`, which the engine
    /// words and orders; nothing is decided here.
    struct DownloadFailure: Equatable, Identifiable {
        struct Next: Equatable {
            let card: String
            let name: String
            /// A cloud candidate until pages may leave: shown, never pressed.
            let needsPermission: Bool
        }
        let steps: [String]
        let model: String
        let reason: String
        let retryJobId: String
        let next: Next?
        var id: String { retryJobId }
        var text: String { "\(model) did not download: \(reason)" }
    }

    /// The engine's typed `download_failed` rows; the candidate's name is the engine's, a row without a step is dropped.
    static func downloadFailures(_ rows: [Components.Schemas.DownloadFailed]) -> [DownloadFailure] {
        rows.compactMap { row in
            guard !row.steps.isEmpty else { return nil }
            let next = row.nextCandidate.map {
                DownloadFailure.Next(card: $0.id, name: $0.name, needsPermission: $0.needsPermission)
            }
            return DownloadFailure(steps: row.steps, model: row.model, reason: row.reason,
                                  retryJobId: row.retryJobId, next: next)
        }
    }

    /// The stages of a recipe run's node, in order; empty for any other job.
    static func stages(of node: ActivityJobNode?) -> [Stage] {
        guard let node else { return [] }
        return node.stages.map { stage in
            let child = stage.childId.flatMap { id in node.children.first { $0.id == id } }
            let account = stage.account
            let counts = account.map(countsWords)
            let running = stage.state == "running"
            return Stage(
                id: stage.id,
                title: child?.displayName ?? cardTitle(stage),
                steps: (stage.steps.count == 1 ? "Step " : "Steps ") + stage.steps.joined(separator: ", "),
                state: stateWords(stage),
                isFailed: stage.state == "failed" || stage.state == "not run",
                counts: counts,
                timeLeft: running ? account?.estimateSecondsLeft.map(ActivityMonitorRow.duration) : nil,
                waitingFor: running ? account?.waitingReason : nil,
                note: stage.note
            )
        }
    }

    /// "12 done · 0 failed · 8 left", and "· first 9 in order" while a page finished ahead of a gap
    /// (`recipes-run.order.done-in-order-shown`, #6186): progress reads in sidebar order.
    static func countsWords(_ account: ActivityRunAccount) -> String {
        let counts = "\(account.pagesDone) done · \(account.pagesFailed) failed · \(account.pagesLeft) left"
        let settled = account.pagesDone + account.pagesFailed
        return account.pagesDoneInOrder < settled ? "\(counts) · first \(account.pagesDoneInOrder) in order" : counts
    }

    private static func cardTitle(_ stage: ActivityRecipeStage) -> String {
        switch stage.card {
        case "check": "Check on the pages"
        case "export": "Write the synced folder"
        case "publish": "Publish the site"
        default: stage.title ?? stage.steps.joined(separator: ", ")
        }
    }

    private static func stateWords(_ stage: ActivityRecipeStage) -> String {
        switch stage.state {
        case "running": "Running"
        case "done": "Done"
        case "waiting": "Waiting for the stage before it"
        case "partial": "Partial: " + (stage.why ?? "some pages could not be read")
        case "failed": "Failed: " + (stage.why ?? "no reason given")
        case "not run": "Not run: " + (stage.why ?? "no reason given")
        case "cancelled": "Stopped"
        default: stage.state
        }
    }

    /// What a recipe run's node says it made, once it has ended; nil before.
    static func summary(of node: ActivityJobNode?) -> Summary? {
        guard let summary = node?.summary else { return nil }
        let failed = summary.failed.map { stage in
            let title = node?.children.first { $0.id == stage.threadId }?.displayName
                ?? stage.steps.joined(separator: ", ")
            let noun = stage.pagesFailed == 1 ? "page" : "pages"
            return Summary.Failed(id: stage.threadId, text: "\(title): \(stage.pagesFailed) \(noun) failed",
                                  offer: stage.offer, threadId: stage.threadId)
        }
        let skipped = summary.skipped.map {
            Summary.Skipped(id: $0.step, text: "\($0.step): \($0.why)", hasFix: $0.fix != nil)
        }
        let download = downloadFailures(summary.downloadFailed ?? [])
        let missed = summary.missed.map { MissedOffer(words: $0.words, offer: $0.offer, folderId: $0.folderId, documents: $0.documents) }
        return Summary(lines: summary.lines ?? [], failed: failed, skipped: skipped, downloadFailed: download, missed: missed)
    }
}
