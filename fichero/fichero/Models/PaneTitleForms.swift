import Foundation

/// The lens title that says what is showing (#6458, `source.editor.pane-title-says-what-is-showing`). Three forms for the pane head's
/// `ViewThatFits` to choose the longest that fits: full "Content · Claude Sonnet · as written ✓", middle "Content · Claude Sonnet",
/// short "Content". The full form is always the tooltip and the accessibility label.
struct PaneTitleForms: Equatable {
    /// Why the shown reading counts: a person chose or wrote it, a machine's is not yet checked, or none counts.
    enum Basis: Equatable {
        case person, machine, none

        /// The SF Symbol the title draws after the text.
        var symbol: String {
            switch self {
            case .person: "checkmark"
            case .machine: "circle"
            case .none: "minus"
            }
        }
    }

    let full: String
    let middle: String
    let short: String
    var tooltip: String { full }
    /// The basis symbol (a check for a person's, a hollow circle for a machine's unchecked, a dash for none); nil with no reading.
    let symbol: String?

    /// - makers: the maker of each line's counting reading (a reader's model or a person); the same maker on every line names it,
    ///   otherwise the title says "N readers". Empty = nothing is read, the title is the lens name.
    /// - level: the shown level, else nil for the working text's level ("as written").
    init(lens: String, makers: [String], level: String?, basis: Basis) {
        short = lens
        let distinct = Array(Set(makers)).sorted()
        guard !distinct.isEmpty else {
            middle = lens
            full = lens
            symbol = nil
            return
        }
        let who = distinct.count == 1 ? distinct[0] : "\(distinct.count) readers"
        middle = "\(lens) · \(who)"
        full = "\(middle) · \(level ?? "as written")"
        symbol = basis.symbol
    }

    private init(full: String, middle: String, short: String) {
        self.full = full
        self.middle = middle
        self.short = short
        symbol = nil
    }

    /// The disagreement lens: "Where the Readers Disagree · 3 readers · 82 %", then "3 readers · 82 %", then the lens name.
    static func disagreement(lens: String, readers: Int, agreementPercent: Int) -> PaneTitleForms {
        let figures = "\(readers) readers · \(agreementPercent) %"
        return PaneTitleForms(full: "\(lens) · \(figures)", middle: figures, short: lens)
    }
}
