import FicheroAPIClient
import SwiftUI

/// Details tab for ClaimInspector showing claim text, type, status, confidence
struct ClaimInspectorDetailsTab: View {
    let claim: Components.Schemas.KnowledgeClaim

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                claimTextSection
                classificationSection
                confidenceSection
                metadataSection
            }
            .padding()
        }
    }

    // MARK: - Claim Text

    private var claimTextSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Claim")
                .font(.subheadline)
                .fontWeight(.semibold)

            Text(claim.text)
                .font(.body)
                .textSelection(.enabled)
        }
    }

    // MARK: - Classification

    private var classificationSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Classification")
                .font(.subheadline)
                .fontWeight(.semibold)

            Form {
                if let claimType = claim.claimType {
                    LabeledContent("Type") {
                        Text(claimType.rawValue.capitalized)
                            .foregroundStyle(.secondary)
                    }
                }

                if let epistemicStatus = claim.epistemicStatus {
                    LabeledContent("Status") {
                        EpistemicStatusBadge(status: epistemicStatus)
                    }
                }

                if let curationState = claim.curationState {
                    LabeledContent("Curation") {
                        CurationStateBadge(state: curationState)
                    }
                }

                if let language = claim.language {
                    LabeledContent("Language") {
                        Text(language.uppercased())
                            .foregroundStyle(.secondary)
                    }
                }

                if let createdBy = claim.createdBy {
                    LabeledContent("Created By") {
                        Text(createdBy.capitalized)
                            .foregroundStyle(.secondary)
                    }
                }
            }
            .formStyle(.grouped)
        }
    }

    // MARK: - Confidence

    private var confidenceSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Confidence")
                .font(.subheadline)
                .fontWeight(.semibold)

            HStack(spacing: 16) {
                if let confidence = claim.confidence {
                    VStack(alignment: .leading) {
                        Text("Assigned")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        ConfidenceBar(value: confidence)
                        Text(String(format: "%.0f%%", confidence * 100))
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }

                if let predicted = claim.predictedConfidence {
                    VStack(alignment: .leading) {
                        Text("Predicted")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        ConfidenceBar(value: predicted)
                        Text(String(format: "%.0f%%", predicted * 100))
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }

                if claim.confidence == nil && claim.predictedConfidence == nil {
                    Text("No confidence data")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
        }
    }

    // MARK: - Metadata

    private var metadataSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Timestamps")
                .font(.subheadline)
                .fontWeight(.semibold)

            Form {
                if let createdAt = claim.createdAt {
                    LabeledContent("Created") {
                        Text(createdAt, style: .date)
                            .foregroundStyle(.secondary)
                    }
                }
                if let updatedAt = claim.updatedAt {
                    LabeledContent("Modified") {
                        Text(updatedAt, style: .relative)
                            .foregroundStyle(.secondary)
                    }
                }
            }
            .formStyle(.grouped)
        }
    }
}

// MARK: - Supporting Views

struct EpistemicStatusBadge: View {
    let status: Components.Schemas.EpistemicStatus

    var body: some View {
        Text(status.rawValue.capitalized)
            .font(.caption)
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .background(backgroundColor)
            .foregroundStyle(foregroundColor)
            .clipShape(RoundedRectangle(cornerRadius: 4))
    }

    private var backgroundColor: Color {
        switch status {
        case .confirmed: return .green.opacity(0.2)
        case .rejected: return .red.opacity(0.2)
        case .tentative: return .orange.opacity(0.2)
        }
    }

    private var foregroundColor: Color {
        switch status {
        case .confirmed: return .green
        case .rejected: return .red
        case .tentative: return .orange
        }
    }
}

struct CurationStateBadge: View {
    let state: Components.Schemas.ClaimCurationState

    var body: some View {
        Text(state.rawValue.capitalized)
            .font(.caption)
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .background(backgroundColor)
            .foregroundStyle(foregroundColor)
            .clipShape(RoundedRectangle(cornerRadius: 4))
    }

    private var backgroundColor: Color {
        switch state {
        case .approved: return .green.opacity(0.2)
        case .rejected: return .red.opacity(0.2)
        case .unreviewed: return .gray.opacity(0.2)
        case .pending: return .orange.opacity(0.2)
        }
    }

    private var foregroundColor: Color {
        switch state {
        case .approved: return .green
        case .rejected: return .red
        case .unreviewed: return .gray
        case .pending: return .orange
        }
    }
}

struct ConfidenceBar: View {
    let value: Double

    var body: some View {
        GeometryReader { geometry in
            ZStack(alignment: .leading) {
                RoundedRectangle(cornerRadius: 2)
                    .fill(Color.gray.opacity(0.3))
                    .frame(height: 4)

                RoundedRectangle(cornerRadius: 2)
                    .fill(confidenceColor)
                    .frame(width: geometry.size.width * value, height: 4)
            }
        }
        .frame(height: 4)
    }

    private var confidenceColor: Color {
        if value >= 0.8 {
            return .green
        } else if value >= 0.5 {
            return .orange
        } else {
            return .red
        }
    }
}
