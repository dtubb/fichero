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

        /// "Read 198 of 203 pages"; "Names: 120 People · 40 Places"; "35 dates · 80 statements".
        let lines: [String]
        let failed: [Failed]
        let skipped: [Skipped]
    }

    /// The stages of a recipe run's node, in order; empty for any other job.
    static func stages(of node: ActivityJobNode?) -> [Stage] {
        guard let node else { return [] }
        return node.stages.map { stage in
            let child = stage.childId.flatMap { id in node.children.first { $0.id == id } }
            let account = stage.account
            let counts = account.map { "\($0.pagesDone) done · \($0.pagesFailed) failed · \($0.pagesLeft) left" }
            let running = stage.state == "running"
            return Stage(
                id: stage.id,
                title: child?.displayName ?? cardTitle(stage),
                steps: (stage.steps.count == 1 ? "Step " : "Steps ") + stage.steps.joined(separator: ", "),
                state: stateWords(stage),
                isFailed: stage.state == "failed" || stage.state == "not run",
                counts: counts,
                timeLeft: running ? account?.estimateSecondsLeft.map(ActivityMonitorRow.duration) : nil,
                waitingFor: running ? account?.waitingReason : nil
            )
        }
    }

    private static func cardTitle(_ stage: ActivityRecipeStage) -> String {
        switch stage.card {
        case "check": "Check on the pages"
        case "export": "Write the synced folder"
        case "publish": "Publish the site"
        default: stage.steps.joined(separator: ", ")
        }
    }

    private static func stateWords(_ stage: ActivityRecipeStage) -> String {
        switch stage.state {
        case "running": "Running"
        case "done": "Done"
        case "waiting": "Waiting for the stage before it"
        case "failed": "Failed: " + (stage.why ?? "no reason given")
        case "not run": "Not run: " + (stage.why ?? "no reason given")
        case "cancelled": "Stopped"
        default: stage.state
        }
    }

    /// What a recipe run's node says it made, once it has ended; nil before.
    static func summary(of node: ActivityJobNode?) -> Summary? {
        guard let summary = node?.summary else { return nil }
        var lines = ["Read \(summary.pagesRead) of \(summary.pages) \(summary.pages == 1 ? "page" : "pages")"]
        let names = summary.names.filter { $0.count > 0 }
        lines.append(names.isEmpty ? "No names found"
                     : "Names: " + names.map { "\($0.count) \($0.label)" }.joined(separator: " · "))
        lines.append("\(summary.dates) \(summary.dates == 1 ? "date" : "dates") · "
                     + "\(summary.statements) \(summary.statements == 1 ? "statement" : "statements")")
        if let proposed = summary.documentsProposed {
            lines.append("\(proposed) \(proposed == 1 ? "document" : "documents") proposed")
        }
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
        return Summary(lines: lines, failed: failed, skipped: skipped)
    }
}
