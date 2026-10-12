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
                Button(smaller.useInsteadTitle) { useSmaller(smaller) }
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

#Preview("A step's candidates: fits, tight, won't fit with a smaller build") {
    VStack(alignment: .leading, spacing: 12) {
        CandidateFitLabel(fit: CandidateFit(
            word: .fits, reason: "needs 3.1 GB with an 8,192-token context; this Mac has 16 GB", smaller: nil
        ))
        CandidateFitLabel(fit: CandidateFit(
            word: .tight, reason: "needs 9.8 GB; other models are unloaded first", smaller: nil
        ))
        CandidateFitLabel(
            fit: CandidateFit(
                word: .wontFit, reason: "needs 11.2 GB with an 8,192-token context; this Mac has 8 GB",
                smaller: CandidateFit.Smaller(
                    card: "mlx:hf/mlx-community/Qwen2.5-VL-3B-Instruct-4bit@main", name: "Qwen2.5-VL 3B (4-bit)"
                )
            ),
            useSmaller: { _ in }
        )
    }
    .padding()
    .frame(width: 420)
}
