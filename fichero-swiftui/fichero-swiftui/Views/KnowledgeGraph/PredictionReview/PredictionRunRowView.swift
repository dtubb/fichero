import FicheroAPIClient
import SwiftUI

// MARK: - Prediction Run Row

struct PredictionRunRow: View {
    let run: Components.Schemas.KnowledgePredictionRun

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Image(systemName: iconForModelType)
                    .foregroundStyle(.secondary)

                Text(run.modelType?.rawValue.capitalized ?? "Unknown")
                    .font(.subheadline)
                    .fontWeight(.medium)

                Spacer()
            }

            if let trainedAt = run.trainedAt {
                Text(trainedAt, style: .relative)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            HStack(spacing: 8) {
                if let mrr = run.mrr {
                    Label(String(format: "MRR: %.2f", mrr), systemImage: "chart.line.uptrend.xyaxis")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }

                if let predictions = run.numPredictions {
                    Label("\(predictions)", systemImage: "sparkles")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }
        }
        .padding(.vertical, 4)
    }

    private var iconForModelType: String {
        guard let modelType = run.modelType else { return "brain" }
        switch modelType {
        case .heuristic: return "wand.and.stars"
        case .pykeen: return "cpu"
        case .openai: return "star"
        case .anthropic: return "person.fill"
        default: return "brain"
        }
    }
}
