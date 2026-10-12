import SwiftUI

/// A candidate's fit under its row (#5641): the word with the engine's reason, and the smaller build as one press
/// ("Use <name> instead", the use-candidate route) where the list holds it and a step can take it. The one view every
/// list of a step's candidates draws it with: Set Up's stage pages, the model finder and the step's card.
struct CandidateFitLabel: View {
    let fit: CandidateFit
    /// Uses the smaller build for the step; nil where no step can take it (the finder outside Set Up).
    var useSmaller: ((CandidateFit.Smaller) -> Void)?

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Label(fit.line, systemImage: fit.systemImage)
                .font(.caption)
                .foregroundStyle(Self.tint(fit.word))
                .fixedSize(horizontal: false, vertical: true)
                .help(fit.line)
            if let smaller = fit.smaller, let useSmaller {
                Button("Use \(smaller.name) instead") { useSmaller(smaller) }
                    .controlSize(.small)
                    .help("Use the smaller build of the same model for this step")
            }
        }
        .accessibilityIdentifier("candidate.fit")
    }

    /// System colours only: a model that fits reads quietly, a tight one warns, one that won't fit is greyed.
    static func tint(_ word: CandidateFit.Word) -> Color {
        switch word {
        case .fits: .secondary
        case .tight: .orange
        case .wontFit: .secondary
        }
    }
}
