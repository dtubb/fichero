import FicheroAPIClient
import SwiftUI

/// View for reviewing and applying AI-generated link predictions
struct PredictionReviewView: View {
    @State private var predictionRuns: [Components.Schemas.KnowledgePredictionRun] = []
    @State private var selectedRun: Components.Schemas.KnowledgePredictionRun?
    @State private var isLoading = false
    @State private var isGenerating = false
    @State private var isApplying = false
    @State private var loadError: String?
    @State private var applyResult: ApplyResult?

    struct ApplyResult: Identifiable {
        let id = UUID()
        let success: Bool
        let message: String
    }

    var body: some View {
        HSplitView {
            runListSidebar
            runDetailPanel
        }
        .frame(minWidth: 400, minHeight: 300)
        .task {
            await loadPredictionRuns()
        }
    }

    // MARK: - Run List Sidebar

    private var runListSidebar: some View {
        VStack(spacing: 0) {
            headerBar
            Divider()
            runList
        }
        .frame(minWidth: 250, maxWidth: 350)
    }

    private var headerBar: some View {
        HStack {
            Text("Predictions")
                .font(.headline)

            Spacer()

            Button {
                Task { await generatePredictions() }
            } label: {
                if isGenerating {
                    ProgressView()
                        .scaleEffect(0.7)
                } else {
                    Image(systemName: "sparkles")
                }
            }
            .help("Generate new predictions")
            .disabled(isGenerating)
        }
        .padding(12)
        .background(Color(.controlBackgroundColor))
    }

    private var runList: some View {
        List(selection: $selectedRun) {
            if isLoading {
                HStack {
                    Spacer()
                    ProgressView()
                    Spacer()
                }
                .listRowBackground(Color.clear)
            } else if let error = loadError {
                VStack(spacing: 8) {
                    Image(systemName: "exclamationmark.triangle")
                        .foregroundStyle(.orange)
                    Text(error)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)
                }
                .padding()
                .listRowBackground(Color.clear)
            } else if predictionRuns.isEmpty {
                VStack(spacing: 8) {
                    Image(systemName: "brain")
                        .font(.system(size: 28))
                        .foregroundStyle(.secondary)
                    Text("No Predictions")
                        .font(.subheadline)
                    Text("Generate predictions to discover potential claim links")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)
                }
                .padding()
                .listRowBackground(Color.clear)
            } else {
                ForEach(predictionRuns, id: \.id) { run in
                    PredictionRunRow(run: run)
                        .tag(run)
                }
            }
        }
        .listStyle(.sidebar)
    }

    // MARK: - Run Detail Panel

    @State private var runPredictions: [Components.Schemas.KnowledgePrediction] = []

    private var runDetailPanel: some View {
        Group {
            if let run = selectedRun {
                VStack(spacing: 0) {
                    runDetailHeader(run)
                    Divider()
                    runDetailMetrics(run)
                    Divider()
                    predictionsList
                }
                .frame(minWidth: 300)
                .task {
                    await loadPredictionsForRun(run)
                }
            } else {
                emptyDetailState
            }
        }
    }

    private func runDetailHeader(_ run: Components.Schemas.KnowledgePredictionRun) -> some View {
        HStack {
            VStack(alignment: .leading, spacing: 4) {
                Text("Prediction Run")
                    .font(.caption)
                    .foregroundStyle(.secondary)

                if let trainedAt = run.trainedAt {
                    Text(trainedAt, style: .date)
                        .font(.subheadline)
                }
            }

            Spacer()

            Button {
                Task { await applyPredictions(run) }
            } label: {
                if isApplying {
                    ProgressView()
                        .scaleEffect(0.7)
                } else {
                    Label("Apply", systemImage: "checkmark.circle")
                }
            }
            .buttonStyle(.borderedProminent)
            .disabled(isApplying)
        }
        .padding(12)
        .background(Color(.controlBackgroundColor))
    }

    private func runDetailMetrics(_ run: Components.Schemas.KnowledgePredictionRun) -> some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 16) {
                MetricCard(
                    title: "Model",
                    value: run.modelType?.rawValue.capitalized ?? "Unknown",
                    icon: "cpu"
                )

                MetricCard(
                    title: "Entities",
                    value: "\(run.numEntities)",
                    icon: "circle.hexagongrid"
                )

                MetricCard(
                    title: "Claims",
                    value: "\(run.numClaims)",
                    icon: "text.alignleft"
                )

                if let mrr = run.mrr {
                    MetricCard(
                        title: "MRR",
                        value: String(format: "%.3f", mrr),
                        icon: "chart.line.uptrend.xyaxis"
                    )
                }

                if let hitsAt10 = run.hitsAt10 {
                    MetricCard(
                        title: "Hits@10",
                        value: String(format: "%.1f%%", hitsAt10 * 100),
                        icon: "target"
                    )
                }

                if let predictions = run.numPredictions {
                    MetricCard(
                        title: "Predictions",
                        value: "\(predictions)",
                        icon: "sparkles"
                    )
                }
            }
            .padding(12)
        }
        .background(Color(.controlBackgroundColor))
    }

    private var predictionsList: some View {
        ScrollView {
            LazyVStack(spacing: 8) {
                if runPredictions.isEmpty {
                    emptyPredictionsState
                } else {
                    ForEach(runPredictions, id: \.id) { prediction in
                        PredictionCard(
                            prediction: prediction,
                            claims: claimsForPrediction(prediction)
                        )
                    }
                }
            }
            .padding()
        }
    }

    private var emptyPredictionsState: some View {
        VStack(spacing: 12) {
            Image(systemName: "chart.bar.xaxis")
                .font(.system(size: 36))
                .foregroundStyle(.secondary)

            Text("No Predictions")
                .font(.headline)

            Text("This run has no predictions to display")
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding(40)
    }

    private var emptyDetailState: some View {
        VStack(spacing: 12) {
            Image(systemName: "brain.head.profile")
                .font(.system(size: 36))
                .foregroundColor(.secondary)

            Text("No Run Selected")
                .font(.headline)

            Text("Select a prediction run to view its details")
                .font(.subheadline)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding()
    }

    // MARK: - Data Loading

    private func loadPredictionRuns() async {
        isLoading = true
        loadError = nil

        do {
            let library = LibraryManager.shared.globalLibrary
            let service = KnowledgeGraphServiceGenerated(apiClient: library!.apiClient)
            predictionRuns = try await service.listPredictions(limit: 20)
        } catch {
            loadError = error.localizedDescription
        }

        isLoading = false
    }

    private func loadPredictionsForRun(_ run: Components.Schemas.KnowledgePredictionRun) async {
        // Predictions are embedded in the run or loaded separately
        // For now, display run-level info
    }

    private func generatePredictions() async {
        isGenerating = true
        loadError = nil

        do {
            let library = LibraryManager.shared.globalLibrary
            let service = KnowledgeGraphServiceGenerated(apiClient: library!.apiClient)
            let newRun = try await service.generateHeuristicPredictions()
            predictionRuns.insert(newRun, at: 0)
            selectedRun = newRun
        } catch {
            loadError = "Generation failed: \(error.localizedDescription)"
        }

        isGenerating = false
    }

    private func applyPredictions(_ run: Components.Schemas.KnowledgePredictionRun) async {
        guard let runId = run.id else { return }

        isApplying = true

        do {
            let library = LibraryManager.shared.globalLibrary
            let service = KnowledgeGraphServiceGenerated(apiClient: library!.apiClient)
            try await service.applyPredictions(runId: runId)
            applyResult = ApplyResult(success: true, message: "Predictions applied successfully")
        } catch {
            applyResult = ApplyResult(success: false, message: "Apply failed: \(error.localizedDescription)")
        }

        isApplying = false
    }

    private func claimsForPrediction(_ prediction: Components.Schemas.KnowledgePrediction) -> (source: Components.Schemas.KnowledgeClaim?, target: Components.Schemas.KnowledgeClaim?) {
        // In a full implementation, we'd load the actual claims
        return (nil, nil)
    }
}

// MARK: - Prediction Run Row

private struct PredictionRunRow: View {
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

// MARK: - Metric Card

private struct MetricCard: View {
    let title: String
    let value: String
    let icon: String

    var body: some View {
        VStack(spacing: 4) {
            Image(systemName: icon)
                .font(.system(size: 16))
                .foregroundStyle(.secondary)

            Text(value)
                .font(.headline)
                .fontWeight(.semibold)

            Text(title)
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
        .frame(minWidth: 70)
        .padding(8)
        .background(Color(.controlBackgroundColor))
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }
}

// MARK: - Prediction Card

private struct PredictionCard: View {
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

// MARK: - Confidence Badge

private struct ConfidenceBadge: View {
    let confidence: Double

    var body: some View {
        HStack(spacing: 4) {
            Circle()
                .fill(confidenceColor)
                .frame(width: 8, height: 8)

            Text(String(format: "%.0f%%", confidence * 100))
                .font(.caption)
                .fontWeight(.medium)
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 4)
        .background(confidenceColor.opacity(0.15))
        .clipShape(RoundedRectangle(cornerRadius: 6))
    }

    private var confidenceColor: Color {
        if confidence >= 0.8 {
            return .green
        } else if confidence >= 0.5 {
            return .orange
        } else {
            return .red
        }
    }
}

// MARK: - Previews

#Preview("Review View") {
    PredictionReviewView()
        .frame(width: 700, height: 500)
}
