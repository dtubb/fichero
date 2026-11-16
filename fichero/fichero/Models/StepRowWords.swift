import Foundation

/// The words a Set Up step row says where no model is chosen or none is needed (`wide.nomodel.fichero-does-this-one`,
/// `wide.nomodel.tie-figures-on-his-pages`, `wide.picker.empty-says-why`). The engine writes the sentences (`how_it_works`, `why`,
/// `fix`, the tie's counts); these only join them. Pure.
enum StepRowWords {
    /// "Fichero does this one: <how it works>" for a job with no model; nil for a job that has a model to choose.
    static func ficheroDoesThisOne(howItWorks: String?) -> String? {
        guard let how = howItWorks?.trimmingCharacters(in: .whitespacesAndNewlines), !how.isEmpty else { return nil }
        return "Fichero does this one: \(how)"
    }

    /// An empty picker says why and what to do, in the engine's words ("No model on this Mac does this yet", "download Qwen3 4B
    /// (2.1 GB) or add a cloud key"); nil when the list has an answer.
    static func emptyPicker(why: String?, fix: String?) -> String? {
        guard let why, !why.isEmpty else { return nil }
        guard let fix, !fix.isEmpty else { return why }
        return "\(why): \(fix)"
    }

    /// The tie's figures after Read's try: "9 lines tied, 2 doubtful, 1 could not be tied; 1 page left as a draft". Nil when the
    /// try has none.
    static func tieFigures(_ counts: SetupStageTryResult.Tie.Counts?) -> String? {
        guard let counts else { return nil }
        let tied = counts.tied ?? 0
        let doubtful = counts.doubtful ?? 0
        let untied = counts.untied ?? 0
        let drafts = counts.drafts ?? 0
        var words = "\(tied) \(tied == 1 ? "line" : "lines") tied, \(doubtful) doubtful, \(untied) could not be tied"
        if drafts > 0 { words += "; \(drafts) \(drafts == 1 ? "page" : "pages") left as a draft" }
        return words
    }

    /// "Show the lines it could not tie" is offered only when there are some: untied, doubtful or a draft page.
    static func offersUntied(_ counts: SetupStageTryResult.Tie.Counts?) -> Bool {
        guard let counts else { return false }
        return (counts.doubtful ?? 0) + (counts.untied ?? 0) + (counts.drafts ?? 0) > 0
    }

    /// Find Lines' two counts for one page: "5 lines on the photograph, 12 on the clarified copy".
    static func lineCounts(_ both: SetupStageTryResult.LineCounts.Both) -> String {
        "\(both.photograph) \(both.photograph == 1 ? "line" : "lines") on the photograph, \(both.clarified) on the clarified copy"
    }

    /// Clarity is off for a faded sample: said with the way to switch it on.
    static let clarityOff = "This page looks faded and Clarity is off: switch it on in Prepare Images to find more lines"
}
