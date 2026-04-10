import FicheroAPIClient
import SwiftUI

/// View for reviewing and applying AI-generated link predictions
struct PredictionReviewView: View {
    @StateObject private var state = PredictionReviewState()

    var body: some View {
        HSplitView {
            runListSidebar
            runDetailPanel
        }
        .frame(minWidth: 400, minHeight: 300)
        .task { await state.loadPredictionRuns() }
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
                Task { await state.generatePredictions() }
            } label: {
                if state.isGenerating {
                    ProgressView()
                        .scaleEffect(0.7)
                } else {
                    Image(systemName: "sparkles")
                }
            }
            .help("Generate new predictions")
            .disabled(state.isGenerating)
        }
        .padding(12)
        .background(Color(.controlBackgroundColor))
    }

    private var runList: some View {
        List(selection: $state.selectedRun) {
            if state.isLoading {
                HStack {
                    Spacer()
                    ProgressView()
                    Spacer()
                }
                .listRowBackground(Color.clear)
            } else if let error = state.loadError {
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
            } else if state.predictionRuns.isEmpty {
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
                ForEach(state.predictionRuns, id: \.id) { run in
                    PredictionRunRow(run: run)
                        .tag(run)
                }
            }
        }
        .listStyle(.sidebar)
    }

    // MARK: - Run Detail Panel

    private var runDetailPanel: some View {
        Group {
            if let run = state.selectedRun {
                VStack(spacing: 0) {
                    runDetailHeader(run)
                    Divider()
                    runDetailMetrics(run)
                    Divider()
                    predictionsList
                }
                .frame(minWidth: 300)
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
                Task { await state.applyPredictions(run) }
            } label: {
                if state.isApplying {
                    ProgressView()
                        .scaleEffect(0.7)
                } else {
                    Label("Apply", systemImage: "checkmark.circle")
                }
            }
            .buttonStyle(.borderedProminent)
            .disabled(state.isApplying)
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
                if state.runPredictions.isEmpty {
                    emptyPredictionsState
                } else {
                    ForEach(state.runPredictions, id: \.id) { prediction in
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

    private func claimsForPrediction(_ prediction: Components.Schemas.KnowledgePrediction) -> PredictionReviewState.ClaimPair {
        (nil, nil)
    }
}

// MARK: - Previews

extension PredictionReviewState {
    typealias ClaimPair = (source: Components.Schemas.KnowledgeClaim?, target: Components.Schemas.KnowledgeClaim?)
}

#Preview("Review View") {
    PredictionReviewView()
        .frame(width: 700, height: 500)
}
