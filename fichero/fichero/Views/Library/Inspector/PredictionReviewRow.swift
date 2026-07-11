import FicheroAPIClient
import SwiftUI

// MARK: - Display mapping (#3447)

/// A PyKEEN stored prediction flattened for review. A stored prediction ranks
/// candidate target entities; the row surfaces the top-ranked one — "source
/// —relation→ predicted target (confidence)" — plus its accept/reject state.
struct PredictionDisplay: Equatable {
    let predictionId: String
    let sourceEntityId: String
    let relation: String
    let predictedEntityId: String
    let predictedEntityName: String
    let confidence: Double
    let isVerified: Bool

    /// Fails only when a stored prediction has no candidate entities to review.
    init?(_ prediction: Components.Schemas.StoredPrediction) {
        // Lowest rank == best candidate (rank 1 is the top hit).
        guard let top = prediction.predictions.min(by: { $0.rank < $1.rank }) else {
            return nil
        }
        predictionId = prediction.predictionId
        sourceEntityId = prediction.sourceEntityId ?? "—"
        relation = prediction.relation ?? "related to"
        predictedEntityId = top.entityId
        predictedEntityName = top.entityName
        confidence = top.confidence
        isVerified = prediction.verified ?? false
    }

    /// "72%" — confidence rendered for the row, clamped to 0…100.
    var confidencePercent: String {
        let clamped = min(max(confidence, 0), 1)
        return "\(Int((clamped * 100).rounded()))%"
    }
}

// MARK: - Review row

/// A PyKEEN link prediction as a review row (#3447): rendered **distinct from
/// asserted claims** (a "Predicted" badge + tinted, dashed frame) with an
/// accept/reject lifecycle — no auto-trust. Persistence flows through
/// `verifyStoredPyKEENPrediction`; here accept/reject are closure seams so the
/// row is context-agnostic and testable. Cross-platform SwiftUI.
struct PredictionReviewRow: View {
    let display: PredictionDisplay
    var onAccept: () async -> Void
    var onReject: () async -> Void

    @State private var isBusy = false

    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: "sparkles")
                .foregroundStyle(.purple)
                .accessibilityHidden(true)

            VStack(alignment: .leading, spacing: 2) {
                Text("\(display.sourceEntityId) \(display.relation) \(display.predictedEntityName)")
                    .font(.callout)
                    .lineLimit(2)
                Text("Predicted · \(display.confidencePercent) confidence")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Spacer(minLength: 6)

            if display.isVerified {
                Label("Accepted", systemImage: "checkmark.seal.fill")
                    .labelStyle(.iconOnly)
                    .foregroundStyle(.green)
                    .help("Accepted prediction")
            } else if isBusy {
                ProgressView().controlSize(.small)
            } else {
                reviewButtons
            }
        }
        .padding(8)
        .background(
            RoundedRectangle(cornerRadius: 8)
                .fill(Color.purple.opacity(0.06))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .strokeBorder(Color.purple.opacity(0.35), style: StrokeStyle(lineWidth: 1, dash: [4, 3]))
        )
        .accessibilityElement(children: .combine)
        .accessibilityLabel(
            "Predicted: \(display.sourceEntityId) \(display.relation) \(display.predictedEntityName), \(display.confidencePercent) confidence"
        )
    }

    private var reviewButtons: some View {
        HStack(spacing: 4) {
            Button {
                run(onReject)
            } label: {
                Image(systemName: "xmark")
            }
            .help("Reject this prediction")
            .accessibilityLabel("Reject prediction")

            Button {
                run(onAccept)
            } label: {
                Image(systemName: "checkmark")
            }
            .help("Accept this prediction")
            .accessibilityLabel("Accept prediction")
        }
        .buttonStyle(.borderless)
    }

    private func run(_ action: @escaping () async -> Void) {
        isBusy = true
        Task {
            await action()
            isBusy = false
        }
    }
}
