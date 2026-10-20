import FicheroAPIClient
import Foundation

/// Whether an MLX candidate fits this Mac to read with (#5641, `runtime.mlx.fit-estimate`), as every list of a step's
/// candidates shows it: Set Up's stage pages, the model finder and the step's own card. The engine decides (the rule
/// the load applies) and words the reason; the app only shows the word, the reason, and the smaller build of the same
/// model as one press when the same list has it. Pure, so each surface says the same and a test can check it.
nonisolated struct CandidateFit: Equatable {  // pure: read from nonisolated canTick
    enum Word: String, Equatable {
        case fits
        case tight
        case wontFit = "won't fit"
    }

    /// The smaller build the engine names, as the candidate in the same list that is it: Use <name> instead.
    struct Smaller: Equatable {
        let card: String
        let name: String

        /// The press's words: "Use Qwen2.5-VL 3B (4-bit) instead".
        var useInsteadTitle: String { "Use \(name) instead" }
    }

    let word: Word
    /// One line in the engine's words: what it needs (weights, KV cache, context) against this Mac.
    let reason: String
    /// The smaller build, when the engine names one and the same list holds it; nil otherwise.
    let smaller: Smaller?

    /// The word as a person reads it beside the model.
    var title: String {
        switch word {
        case .fits: "Fits this Mac"
        case .tight: "Tight on this Mac"
        case .wontFit: "Won't fit this Mac"
        }
    }

    var systemImage: String {
        switch word {
        case .fits: "checkmark.circle"
        case .tight: "exclamationmark.circle"
        case .wontFit: "xmark.circle"
        }
    }

    /// A model that won't fit is greyed out with its reason, never hidden, and offers no use of itself.
    var isGreyed: Bool { word == .wontFit }

    /// The word and the reason in one line, for the help and under the row.
    var line: String { "\(title): \(reason)" }

    /// The candidate's fit, or nil for a model the engine gives none (any model that is not MLX). The contract's enum
    /// holds the three words, so a fourth fails at decoding, never here.
    static func of(_ candidate: Components.Schemas.ModelCandidate,
                   in list: [Components.Schemas.ModelCandidate]) -> CandidateFit? {
        guard let fit = candidate.fit else { return nil }
        return make(word: fit.word.rawValue, reason: fit.reason, smaller: fit.smaller, of: candidate, in: list)
    }

    /// The mapping itself, from the engine's three fields.
    static func make(word: String, reason: String, smaller: String?,
                     of candidate: Components.Schemas.ModelCandidate?,
                     in list: [Components.Schemas.ModelCandidate]) -> CandidateFit? {
        guard let known = Word(rawValue: word) else { return nil }
        let build = smaller.flatMap { name in
            list.first { $0.id != candidate?.id && matches($0, smaller: name) }
                .map { Smaller(card: $0.id, name: $0.name) }
        }
        return CandidateFit(word: known, reason: reason, smaller: build)
    }

    /// The engine names the smaller build by its display name, else its Hub repo; a card's id carries the repo
    /// (`mlx:hf/<repo>@<revision>`).
    static func matches(_ candidate: Components.Schemas.ModelCandidate, smaller: String) -> Bool {
        candidate.name == smaller || candidate.id.contains("/\(smaller)@") || candidate.id.hasSuffix("/\(smaller)")
    }

    /// The fit of the model a step uses now: the candidate the engine marks chosen for it, else the one whose card
    /// the step names.
    static func ofStep(card: String?, in list: [Components.Schemas.ModelCandidate]) -> CandidateFit? {
        let current = list.first { $0.chosen == true } ?? list.first { $0.id == card }
        return current.flatMap { of($0, in: list) }
    }
}
