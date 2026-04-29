import FicheroAPIClient
import SwiftUI

// MARK: - Prediction Card

struct PredictionCard: View {
    let prediction: Components.Schemas.KnowledgePrediction
    let claims: (source: Components.Schemas.KnowledgeClaim?, target: Components.Schemas.KnowledgeClaim?)

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Image(systemName: "arrow.right.circle")
                    .foregroundStyle(.accentColor)

                Text("Link Prediction")
                    .font(.subheadline)
                    .fontWeight(.medium)

                Spacer()

                if let confidence = prediction.predictedConfidence {
                    ConfidenceBadge(confidence: confidence)
                }
            }

            if let sourceId = prediction.sourceClaimId {
                LabeledContent("Source") {
                    Text(sourceId)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .textSelection(.enabled)
                }
            }

            if let targetId = prediction.targetClaimId {
                LabeledContent("Target") {
                    Text(targetId)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .textSelection(.enabled)
                }
            }

            if let relationType = prediction.relationType {
                LabeledContent("Relation") {
                    Text(relationType)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
        }
        .padding(12)
        .background(Color(.controlBackgroundColor))
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }
}
