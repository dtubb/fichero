import FicheroAPIClient
import Foundation

/// What a person can do in place when the cloud spend caps stop (or would stop) a run (#6295, `ai.where.cloud-spend-cap`):
/// the engine's `cloud_cap` line read as words and offers. The amounts are the engine's (`needed_cap_usd`,
/// `needed_project_cap_usd`, `project_remaining_usd`, `fewer_pages`): the best estimate, no margin; nothing is worked out here.
/// Pure, for the tests.
struct CloudCapFix: Equatable {
    /// "Raise the monthly cap to $18.00": the cap to set, in dollars.
    struct Raise: Equatable {
        let usd: Double
        let title: String
    }

    /// Set the monthly cap, when the estimate is over what it leaves.
    let monthly: Raise?
    /// Set the project's total cap, when the estimate is over what it leaves.
    let project: Raise?
    /// Run only this many of the first pages (Finder order), when that fits what the caps leave.
    let firstPages: Int?
    /// The reason in plain words; nil when the run is not over a cap.
    let reason: String?

    var isOffered: Bool { monthly != nil || project != nil }

    nonisolated init(_ line: Components.Schemas.CloudCapLine) {
        guard line.over, let estimate = line.estimateUsd else {
            monthly = nil
            project = nil
            firstPages = nil
            reason = nil
            return
        }
        monthly = line.overMonth == true ? line.neededCapUsd.map { Raise(usd: $0, title: "Raise the monthly cap to \(Self.usd($0))") } : nil
        project = line.overProject == true
            ? line.neededProjectCapUsd.map { Raise(usd: $0, title: "Raise the project cap to \(Self.usd($0))") } : nil
        firstPages = line.fewerPages
        var parts: [String] = []
        if line.overMonth == true {
            parts.append("the monthly cap (\(Self.usd(line.capUsd))) leaves \(Self.usd(line.remainingUsd))")
        }
        if line.overProject == true, let cap = line.projectCapUsd {
            parts.append("the project's total cap (\(Self.usd(cap))) leaves \(Self.usd(line.projectRemainingUsd ?? 0))")
        }
        reason = "This run is estimated at \(Self.usd(estimate)), more than " + parts.joined(separator: " and ") + "."
    }

    /// A run paused at a cap, as the engine says it (`stopped_at_cap`, #6295): its words and the cap, to the cent, under which the
    /// refused call would have been sent. The plan cannot say it: its estimate may fit while one call's worst case does not.
    struct Stop: Equatable {
        let words: String
        let monthly: Raise?
        let project: Raise?

        nonisolated init?(_ status: Components.Schemas.RecipeRunStatus) {
            guard status.stoppedAtCap == true else { return nil }
            words = status.reason ?? "Paused at the cloud spend cap"
            monthly = status.stoppedNeedsCapUsd.map { Raise(usd: $0, title: "Raise the monthly cap to \(CloudCapFix.usd($0))") }
            project = status.stoppedNeedsProjectCapUsd.map { Raise(usd: $0, title: "Raise the project cap to \(CloudCapFix.usd($0))") }
        }

        nonisolated init(words: String, monthly: Raise? = nil, project: Raise? = nil) {
            self.words = words
            self.monthly = monthly
            self.project = project
        }
    }

    nonisolated static func usd(_ value: Double) -> String { value.formatted(.currency(code: "USD")) }

    /// "Run the first 40 pages": the engine's count of the first pages that fit.
    nonisolated static func firstPagesTitle(_ count: Int) -> String {
        count == 1 ? "Run the first page" : "Run the first \(count) pages"
    }

    /// The estimate's basis, a line per run: its pages, what it is priced at, and its cost, so the figure beside the cap can be
    /// checked ("Read lines: 120 pages · the model's listed rate · $2.71"). `title` names a run's steps.
    nonisolated static func basis(of estimate: Components.Schemas.StartEstimate, title: (String) -> String) -> [String] {
        estimate.runs.map { run in
            let name = run.steps.map(title).joined(separator: ", ")
            var parts = ["\(run.pages) \(run.pages == 1 ? "page" : "pages")"]
            if let calls = run.callsPerPage, calls > 1 { parts.append("\(calls) calls a page") }
            parts.append(run.basis ?? (run.costUsd == nil ? "unpriced" : "estimated"))
            parts.append(run.costUsd.map(Self.usd) ?? "price unknown")
            return "\(name): " + parts.joined(separator: " · ")
        }
    }

    /// The plan's refusals without the cap's own: the cap row says that one, with its fixes, so the list does not say it twice. The
    /// engine names the sentence it added (`cloud_cap.refusal`); no words are matched here.
    nonisolated static func withoutCapRefusal(_ refusals: [String], line: Components.Schemas.CloudCapLine?) -> [String] {
        guard let said = line?.refusal else { return refusals }
        return refusals.filter { $0 != said }
    }

    /// Whether the plan is over a cap, so a refused Start has fixes to offer (`cloud_cap.over`), whatever the refusal's words.
    nonisolated static func isOver(_ line: Components.Schemas.CloudCapLine?) -> Bool { line?.over == true }
}
