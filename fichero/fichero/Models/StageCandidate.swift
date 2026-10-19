import Foundation

/// One candidate's go at a stage's sample pages (#5668, `source.onboard.stages.compares-candidates`): the bake-off
/// row's fields (its card, name, where it runs, its cost) with its own result on the samples and how it compared, in
/// the shape the stage's try answers (`candidates`, the engine's 8f2635889). A column of the A/B/C comparison.
struct StageCandidate: Decodable, Equatable, Identifiable {
    struct Cost: Decodable, Equatable {
        let value: Double?
        let basis: String?
    }

    typealias Measures = StageCandidateMeasures

    let card: String
    let name: String?
    let runsOn: String?
    let local: Bool?
    /// Character error rate against a checked reading, 0–1; nil when nothing was checked.
    let cer: Double?
    /// Agreement with the other candidates, 0–1, when there is no checked reading.
    let agreement: Double?
    let seconds: Double?
    let costUsd: Cost?
    /// Why it has no score, or did not run, in the engine's words.
    let why: String?
    /// Its run's state: done, failed, skipped.
    let state: String?
    let perPage: [SetupStageTryResult.Page]?
    let names: [SetupStageTryResult.Name]?
    let measures: Measures?
    /// Where this model is on the try, shown in place (`source.onboard.stages.try-progress-in-place`).
    let progress: Progress?

    struct Progress: Decodable, Equatable {
        let state: String
        let done: Int
        let total: Int
        let page: String?
        let step: String?
        let waitingFor: String?

        enum CodingKeys: String, CodingKey {
            case state, done, total, page, step
            case waitingFor = "waiting_for"
        }
    }

    var id: String { card }

    /// "Kraken: page 2 of 5, finding lines", or "Kraken: waiting, …"; nil once it is done, failed or stopped.
    var progressWords: String? {
        guard let progress, progress.state == "running" || progress.state == "waiting" else { return nil }
        if progress.state == "waiting" || progress.total == 0 {
            return "\(title): waiting" + (progress.waitingFor.map { ", \($0)" } ?? "")
        }
        let at = min(progress.done + 1, progress.total)
        return "\(title): page \(at) of \(progress.total)" + (progress.step.map { ", \($0)" } ?? "")
    }

    enum CodingKeys: String, CodingKey {
        case card, name, local, cer, agreement, seconds, why, state, names, measures, progress
        case runsOn = "runs_on"
        case costUsd = "cost_usd"
        case perPage = "per_page"
    }

    /// Its column's title: its name, else its card.
    var title: String { name ?? card }

    /// Runs on this Mac: free.
    var runsHere: Bool { local == true || (runsOn ?? "").hasPrefix("this-mac") }

    /// How it compared, in words, by kind: "4.1% character errors" or "80% agreement" (text), "80% overlap"
    /// (shapes), "found 12, 3 only here" (items); else the row's own score, else why it has none.
    var quality: String? {
        if let measures, let said = Self.words(measures) { return said }
        if let cer { return Self.percent(cer, digits: 1) + " character errors" }
        if let agreement { return Self.percent(agreement, digits: 0) + " agreement" }
        return why
    }

    static func words(_ measures: Measures) -> String? {
        switch measures.kind {
        case "shapes":
            return measures.agreement.map { percent($0, digits: 0) + " overlap" } ?? measures.notMeasured
        case "items":
            guard let found = measures.found else { return nil }
            return "found \(found)" + (measures.onlyThisFound.map { ", \($0) only here" } ?? "")
        default:
            if let cer = measures.cer { return percent(cer, digits: 1) + " character errors" }
            return measures.agreement.map { percent($0, digits: 0) + " agreement" } ?? measures.notMeasured
        }
    }

    private static func percent(_ share: Double, digits: Int) -> String {
        share.formatted(.percent.precision(.fractionLength(digits)))
    }

    /// What it measured, in words, for under its column: how it compared, how long, and what it costs ("free, on
    /// this Mac" or the cloud's price).
    var measureWords: [String] {
        var said: [String] = []
        if let quality { said.append(quality) }
        if let seconds { said.append("\(Int(seconds.rounded())) s") }
        if runsHere {
            said.append("free, on this Mac")
        } else if let value = costUsd?.value {
            // A price in US dollars reads "$0.04" everywhere; the machine's locale would say "US$0.04" in Canada.
            let price = value.formatted(.currency(code: "USD").locale(Locale(identifier: "en_US")))
            said.append(costUsd?.basis == "estimate" ? "about \(price)" : price)
        } else {
            said.append("price not known")
        }
        return said
    }

    /// Its result on the samples, as its column's picture plays it; nil when it made nothing.
    var showcase: StageShowcase? {
        StageShowcaseSource.own(pages: perPage ?? [], names: names ?? [])
    }

    /// The columns to show: the engine's candidates, at most three; one column when there is one.
    static func columns(_ candidates: [StageCandidate]?) -> [StageCandidate] {
        Array((candidates ?? []).prefix(3))
    }
}

/// How a candidate compared, by what the stage makes: `text` (agreement, and CER on lines a person corrected),
/// `shapes` (overlap with the other candidates' regions or lines), `items` (names, statements or dates found, and how
/// many only this one found).
struct StageCandidateMeasures: Decodable, Equatable {
    let kind: String
    let agreement: Double?
    let cer: Double?
    let found: Int?
    let onlyThisFound: Int?
    /// Why it has no figure, in the engine's words ("nothing to compare with: the other candidates found no lines"):
    /// shown where the percentage would be, so a missing figure is never read as 0%.
    let notMeasured: String?

    enum CodingKeys: String, CodingKey {
        case kind, agreement, cer, found
        case onlyThisFound = "only_this_found"
        case notMeasured = "not_measured"
    }

    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        kind = try values.decode(String.self, forKey: .kind)
        agreement = try values.decodeIfPresent(Double.self, forKey: .agreement)
        cer = try values.decodeIfPresent(Double.self, forKey: .cer)
        found = try values.decodeIfPresent(Int.self, forKey: .found)
        notMeasured = try values.decodeIfPresent(String.self, forKey: .notMeasured)
        // The engine lists the names only this one found; the count is what the column says.
        if let count = try? values.decodeIfPresent(Int.self, forKey: .onlyThisFound) {
            onlyThisFound = count
        } else {
            onlyThisFound = try values.decodeIfPresent([String].self, forKey: .onlyThisFound)?.count
        }
    }
}

/// Which candidates the person asked to compare (`source.onboard.stages.compares-candidates`): at most three, in
/// the order ticked; none means the engine's own choice (the step's own model and its next one or two).
enum StageCandidateChoice {
    static let most = 3

    /// Tick or untick a card; a fourth is not taken.
    static func toggle(_ card: String, in chosen: [String]) -> [String] {
        if chosen.contains(card) { return chosen.filter { $0 != card } }
        return chosen.count < most ? chosen + [card] : chosen
    }

    /// The request's `candidates`: the cards chosen, or nil for the engine's own choice.
    static func request(_ chosen: [String]) -> [String]? {
        chosen.isEmpty ? nil : chosen
    }
}

extension RecipeSetupStore {
    /// The recipe's step that does one of these jobs (a stage's), for Use This.
    func stepId(forJobs jobs: [String]) -> String? {
        recipe?.steps.first { jobs.contains($0.job) }?.id
    }

    /// The stage's main step, with its job, for listing who could do it.
    func mainStep(forJobs jobs: [String]) -> (id: String, job: String)? {
        guard let step = recipe?.steps.first(where: { jobs.contains($0.job) }) else { return nil }
        return (step.id, step.job)
    }
}
