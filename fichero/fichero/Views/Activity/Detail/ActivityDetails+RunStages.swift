import FicheroAPIClient
import Foundation

/// Set Up's stages (`source/models-chains-and-projects.md` §7c and §7d, ruled 2026-10-11, #5668), in pipeline
/// order, by the jobs each carries: thirteen, as the engine's `recipes/stages.py` lists them. A recipe run's
/// details, the Activity popover and the run strip read a run by these stages, so a run reads the same everywhere
/// (#5670).
///
/// ponytail: a table in the app, kept in step with the engine's list by hand; Set Up reads that list itself
/// (`RecipeSetupStore.loadStages`). Read it here too when Activity has a store to hold it.
enum SetupStages {
    struct Stage: Equatable {
        let id: String
        let title: String
        let jobs: [String]
    }

    static let all: [Stage] = [
        Stage(id: "prepare-images", title: "Prepare Images", jobs: ["split-pages", "prepare-the-image"]),
        Stage(id: "find-regions", title: "Find Regions", jobs: ["find-regions"]),
        Stage(id: "find-lines", title: "Find Lines", jobs: ["find-lines", "put-in-order", "refine-shapes"]),
        Stage(id: "read", title: "Read",
              jobs: ["read-a-line", "read-a-page", "correct", "tie-text-to-lines", "transcribe-speech"]),
        Stage(id: "normalise", title: "Normalise", jobs: ["translate-transliterate-normalise"]),
        // Translate shares Normalise's job in the engine until it has its own: a run's step reads under Normalise.
        Stage(id: "translate", title: "Translate", jobs: []),
        Stage(id: "organise", title: "Organise", jobs: ["find-documents-in-a-folder", "split-into-entries"]),
        Stage(id: "names", title: "Names", jobs: ["find-names-tag-words", "place-in-a-gazetteer", "link-to-authorities"]),
        Stage(id: "statements", title: "Statements", jobs: ["find-statements"]),
        Stage(id: "dates", title: "Dates & Times", jobs: ["work-out-dates"]),
        Stage(id: "passages", title: "Passages", jobs: ["pull-out-passages"]),
        Stage(id: "structured-data", title: "Structured Data",
              jobs: ["find-a-tables-cells", "extract-to-a-table", "describe-for-the-catalogue"]),
        Stage(id: "search", title: "Search", jobs: ["make-a-vector"])
    ]

    /// The stage a recipe step belongs to, by its id or its job; nil for a step no stage carries (a check, an export).
    static func stage(of step: String) -> Stage? {
        all.first { $0.jobs.contains(step) }
    }
}

/// Where a stage of a recipe run got to (#5670).
enum ActivityStageCardState: Equatable {
    case done, partial, running, waiting, notRun, skipped, failed, unknown
}

extension ActivityDetails {
    /// One of Set Up's stages in a recipe run (#5670): its state, a bar of its pages, what it made and, when it did not
    /// run, why in one short sentence. Never a step id.
    struct StageCard: Equatable, Identifiable {
        /// The stage's id in Set Up (`SetupStages`), which Open Set Up… goes to.
        let id: String
        let title: String
        let state: ActivityStageCardState
        /// Its pages done and in all; 0 of 0 when it has none to count.
        let done: Int
        let total: Int
        /// What it made: "Read 91 of 92 pages", "73 People · 69 Places · 18 Organisations".
        let made: [String]
        /// Why it did not run or was skipped, in one short sentence.
        let why: String?
        /// Set Up has a fix for why it was skipped.
        let offersSetUp: Bool
        /// Its pages that failed, with Read Again.
        let failed: Summary.Failed?

        var stateWords: String {
            switch state {
            case .done: "Done"
            case .partial: "Partial"
            case .running: "Running"
            case .waiting: "Waiting"
            case .notRun: "Not run"
            case .skipped: "Skipped"
            case .failed: "Failed"
            case .unknown: "Unknown"
            }
        }
    }

    /// A recipe run's node as Set Up's stages, in Set Up's order: each stage the run ran, or the plan skipped. Empty
    /// for any other job.
    static func stageCards(of node: ActivityJobNode?) -> [StageCard] {
        guard let node, !node.stages.isEmpty || node.summary != nil else { return [] }
        let summary = node.summary
        return SetupStages.all.compactMap { stage in
            let runs = node.stages.filter { run in
                (run.steps + [run.job].compactMap { $0 }).contains { SetupStages.stage(of: $0) == stage }
            }
            let skipped = (summary?.skipped ?? []).filter { SetupStages.stage(of: $0.step) == stage }
            guard !runs.isEmpty || !skipped.isEmpty else { return nil }
            let state: ActivityStageCardState = runs.isEmpty ? .skipped : Self.state(of: runs.map(\.state))
            let account = runs.compactMap(\.account).max { $0.pagesTotal < $1.pagesTotal }
            let failedStage = summary?.failed.first { failure in runs.contains { $0.childId == failure.threadId } }
            let why: String? = switch state {
            case .skipped: skipped.first.map { Self.oneSentence($0.why) }
            case .notRun, .failed, .partial: runs.compactMap(\.why).first.map(Self.oneSentence)
            default: nil
            }
            return StageCard(
                id: stage.id, title: stage.title, state: state,
                done: account?.pagesDone ?? 0, total: account?.pagesTotal ?? 0,
                made: state == .skipped || state == .notRun ? [] : Self.made(stage.id, summary: summary),
                why: why, offersSetUp: skipped.contains { $0.fix != nil },
                failed: failedStage.map { failure in
                    let noun = failure.pagesFailed == 1 ? "page" : "pages"
                    return Summary.Failed(id: failure.threadId, text: "\(failure.pagesFailed) \(noun) failed",
                                          offer: failure.offer, threadId: failure.threadId)
                }
            )
        }
    }

    /// A stage carried by several runs reads as its most telling one: failed, then running, waiting, not run, done.
    private static func state(of states: [String]) -> ActivityStageCardState {
        if states.contains("failed") { return .failed }
        if states.contains("running") { return .running }
        if states.contains("waiting") { return .waiting }
        // some pages lost: never read as done (`activity.run.step-honest-about-lost-pages`)
        if states.contains("partial") { return .partial }
        if states.contains(where: { $0 == "not run" || $0 == "cancelled" }) { return .notRun }
        if states.contains("interrupted") { return .failed }
        if states.allSatisfy({ ["done", "completed", "complete", "finished"].contains($0) }) { return .done }
        return .unknown  // a state nobody here knows is never Done (#5957)
    }

    /// What a stage made, from the run's summary (the engine counts; this only words it).
    private static func made(_ stage: String, summary: Components.Schemas.RecipeRunSummary?) -> [String] {
        guard let summary else { return [] }
        switch stage {
        case "read":
            return summary.pages > 0 ? ["Read \(summary.pagesRead) of \(summary.pages) \(plural(summary.pages, "page"))"] : []
        case "names":
            let kinds = summary.names.filter { $0.count >= 1 }
            return [kinds.isEmpty ? "No names found" : kinds.map { "\($0.count) \($0.label)" }.joined(separator: " · ")]
        case "dates":
            return ["\(summary.dates) \(plural(summary.dates, "date"))"]
        case "statements":
            return ["\(summary.statements) \(plural(summary.statements, "statement"))"]
        case "organise":
            var lines: [String] = []
            // "N documents proposed, M applied" (`finddocs.review.activity`): applied by the run's own level or by
            // a person since; the rest wait in Items.
            if let proposed = summary.documentsProposed {
                let applied = summary.documentsAccepted.map { ", \($0) applied" } ?? ""
                lines.append("\(proposed) \(plural(proposed, "document")) proposed\(applied)")
            }
            if let groups = summary.groupsProposed, groups > 0 {
                lines.append("\(groups) \(plural(groups, "group")) proposed")
            }
            if let entries = summary.entries { lines.append("\(entries) dated \(plural(entries, "entry", "entries"))") }
            return lines
        default:
            return []
        }
    }

    private static func plural(_ count: Int, _ one: String, _ many: String? = nil) -> String {
        count == 1 ? one : (many ?? one + "s")
    }

    /// The engine's reason as one short sentence (#5670): a leading step id ("find-statements: …") taken off, then
    /// its first sentence, and at most about a line.
    static func oneSentence(_ why: String) -> String {
        var text = why.trimmingCharacters(in: .whitespaces)
        // A step id is one word of lowercase letters, digits and hyphens: "find-statements: no model…".
        if let colon = text.firstIndex(of: ":") {
            let head = text[..<colon]
            if !head.isEmpty, head.allSatisfy({ $0.isLowercase || $0.isNumber || $0 == "-" || $0 == "_" }) {
                text = text[text.index(after: colon)...].trimmingCharacters(in: .whitespaces)
            }
        }
        if let end = text.range(of: ". ") { text = String(text[..<end.lowerBound]) }
        if text.hasSuffix(".") { text.removeLast() }
        if text.count > 110, let space = text.prefix(110).lastIndex(of: " ") {
            text = String(text[..<space]) + "…"
        }
        guard let first = text.first else { return text }
        return first.uppercased() + text.dropFirst() + (text.hasSuffix("…") ? "" : ".")
    }
}
