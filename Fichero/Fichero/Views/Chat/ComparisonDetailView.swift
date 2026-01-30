import SwiftUI
import OSLog

private let logger = Logger(subsystem: "ca.tubb.Fichero", category: "ComparisonDetailView")

/// Full comparison detail from the API
struct ComparisonDetail: Codable, Identifiable {
    var id: String { comparisonId }
    let prompt: String
    let modelsCompared: [String]
    let results: [ModelResultDetail]
    let fastestModel: String?
    let cheapestModel: String?
    let totalCostUsd: Double
    let totalLatencyMs: Double
    let comparisonId: String
    let timestamp: String

    enum CodingKeys: String, CodingKey {
        case prompt
        case modelsCompared = "models_compared"
        case results
        case fastestModel = "fastest_model"
        case cheapestModel = "cheapest_model"
        case totalCostUsd = "total_cost_usd"
        case totalLatencyMs = "total_latency_ms"
        case comparisonId = "comparison_id"
        case timestamp
    }
}

/// Individual model result in a comparison
struct ModelResultDetail: Codable, Identifiable {
    var id: String { "\(provider)-\(model)" }
    let provider: String
    let model: String
    let response: String
    let latencyMs: Double
    let inputTokens: Int
    let outputTokens: Int
    let costUsd: Double
    let error: String?
    let timestamp: String

    enum CodingKeys: String, CodingKey {
        case provider
        case model
        case response
        case latencyMs = "latency_ms"
        case inputTokens = "input_tokens"
        case outputTokens = "output_tokens"
        case costUsd = "cost_usd"
        case error
        case timestamp
    }
}

/// Detail view for a model comparison showing all model responses
struct ComparisonDetailView: View {
    let comparisonSummary: ComparisonSummary
    @EnvironmentObject var apiClient: APIClient

    @State private var comparison: ComparisonDetail?
    @State private var isLoading = true
    @State private var error: String?
    @State private var selectedModelId: String?
    @State private var showRawJSON = false

    var body: some View {
        Group {
            if isLoading {
                ProgressView("Loading comparison...")
            } else if let error = error {
                errorView(error)
            } else if let comparison = comparison {
                comparisonContent(comparison)
            }
        }
        .task {
            guard !Task.isCancelled else { return }
            await loadComparison()
        }
    }

    // MARK: - Error View

    @ViewBuilder
    private func errorView(_ message: String) -> some View {
        ContentUnavailableView {
            Label("Failed to Load", systemImage: "exclamationmark.triangle")
        } description: {
            Text(message)
        } actions: {
            Button("Retry") {
                Task { await loadComparison() }
            }
        }
    }

    // MARK: - Comparison Content

    @ViewBuilder
    private func comparisonContent(_ comparison: ComparisonDetail) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                // Header
                headerSection(comparison)

                Divider()

                // Prompt
                promptSection(comparison)

                Divider()

                // Summary stats
                statsSection(comparison)

                Divider()

                // Model responses
                responsesSection(comparison)
            }
            .padding()
        }
    }

    // MARK: - Header Section

    @ViewBuilder
    private func headerSection(_ comparison: ComparisonDetail) -> some View {
        HStack {
            VStack(alignment: .leading, spacing: 4) {
                Text("Model Comparison")
                    .font(.title2.bold())

                Text("\(comparison.modelsCompared.count) models compared")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }

            Spacer()

            // Action buttons
            HStack(spacing: 8) {
                Button {
                    showRawJSON.toggle()
                } label: {
                    Label("JSON", systemImage: "curlybraces")
                }
                .buttonStyle(.bordered)

                Button {
                    Task { await rerunComparison(comparison) }
                } label: {
                    Label("Re-run", systemImage: "arrow.clockwise")
                }
                .buttonStyle(.borderedProminent)
            }
        }
    }

    // MARK: - Prompt Section

    @ViewBuilder
    private func promptSection(_ comparison: ComparisonDetail) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Prompt")
                .font(.headline)

            Text(comparison.prompt)
                .font(.body)
                .padding(12)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Color(nsColor: .textBackgroundColor))
                .cornerRadius(8)
                .textSelection(.enabled)
        }
    }

    // MARK: - Stats Section

    @ViewBuilder
    private func statsSection(_ comparison: ComparisonDetail) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Summary")
                .font(.headline)

            HStack(spacing: 24) {
                statCard(
                    title: "Total Cost",
                    value: String(format: "$%.4f", comparison.totalCostUsd),
                    icon: "dollarsign.circle"
                )

                statCard(
                    title: "Total Latency",
                    value: formatLatency(comparison.totalLatencyMs),
                    icon: "clock"
                )

                if let fastest = comparison.fastestModel {
                    statCard(
                        title: "Fastest",
                        value: formatModelName(fastest),
                        icon: "bolt.fill",
                        color: .green
                    )
                }

                if let cheapest = comparison.cheapestModel {
                    statCard(
                        title: "Cheapest",
                        value: formatModelName(cheapest),
                        icon: "leaf.fill",
                        color: .mint
                    )
                }
            }
        }
    }

    @ViewBuilder
    private func statCard(title: String, value: String, icon: String, color: Color = .blue) -> some View {
        VStack(spacing: 4) {
            HStack(spacing: 4) {
                Image(systemName: icon)
                    .foregroundStyle(color)
                Text(title)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Text(value)
                .font(.subheadline)
                .fontWeight(.medium)
        }
        .padding(12)
        .background(Color(nsColor: .controlBackgroundColor))
        .cornerRadius(8)
    }

    // MARK: - Responses Section

    @ViewBuilder
    private func responsesSection(_ comparison: ComparisonDetail) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Responses")
                .font(.headline)

            ForEach(comparison.results) { result in
                modelResponseCard(result, comparison: comparison)
            }
        }
    }

    @ViewBuilder
    private func modelResponseCard(_ result: ModelResultDetail, comparison: ComparisonDetail) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            // Model header
            HStack {
                providerIcon(result.provider)
                    .frame(width: 24, height: 24)

                VStack(alignment: .leading, spacing: 2) {
                    Text(result.model)
                        .font(.subheadline)
                        .fontWeight(.medium)

                    Text(result.provider.capitalized)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                Spacer()

                // Badges
                HStack(spacing: 8) {
                    if result.model == comparison.fastestModel {
                        Badge(text: "Fastest", color: .green, icon: "bolt.fill")
                    }
                    if result.model == comparison.cheapestModel {
                        Badge(text: "Cheapest", color: .mint, icon: "leaf.fill")
                    }
                }

                // Stats
                HStack(spacing: 12) {
                    VStack(alignment: .trailing, spacing: 2) {
                        Text(formatLatency(result.latencyMs))
                            .font(.caption)
                            .fontWeight(.medium)
                        Text("latency")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }

                    VStack(alignment: .trailing, spacing: 2) {
                        Text(String(format: "$%.4f", result.costUsd))
                            .font(.caption)
                            .fontWeight(.medium)
                        Text("cost")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }

                    VStack(alignment: .trailing, spacing: 2) {
                        Text("\(result.inputTokens + result.outputTokens)")
                            .font(.caption)
                            .fontWeight(.medium)
                        Text("tokens")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                }
            }

            Divider()

            // Response content
            if let error = result.error {
                HStack {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .foregroundStyle(.red)
                    Text(error)
                        .font(.caption)
                        .foregroundStyle(.red)
                }
            } else {
                Text(result.response)
                    .font(.body)
                    .textSelection(.enabled)
            }
        }
        .padding(16)
        .background(Color(nsColor: .controlBackgroundColor))
        .cornerRadius(12)
    }

    @ViewBuilder
    private func providerIcon(_ provider: String) -> some View {
        let (icon, color): (String, Color) = {
            switch provider.lowercased() {
            case "openai": return ("brain.head.profile", .green)
            case "anthropic": return ("sparkles", .orange)
            case "google": return ("g.circle.fill", .blue)
            case "mistral": return ("m.circle.fill", .purple)
            default: return ("server.rack", .secondary)
            }
        }()

        Image(systemName: icon)
            .font(.title3)
            .foregroundStyle(color)
    }

    // MARK: - Helpers

    private func formatLatency(_ ms: Double) -> String {
        if ms < 1000 {
            return String(format: "%.0fms", ms)
        } else {
            return String(format: "%.1fs", ms / 1000)
        }
    }

    private func formatModelName(_ model: String) -> String {
        // Shorten long model names
        if model.count > 20 {
            return String(model.prefix(17)) + "..."
        }
        return model
    }

    // MARK: - Actions

    private func loadComparison() async {
        isLoading = true
        error = nil

        do {
            let url = URL(string: "http://localhost:8765/api/model-comparison/comparison/\(comparisonSummary.comparisonId)")!
            let (data, response) = try await URLSession.shared.data(from: url)

            guard let httpResponse = response as? HTTPURLResponse else {
                throw URLError(.badServerResponse)
            }

            if httpResponse.statusCode == 404 {
                self.error = "Comparison not found"
            } else if httpResponse.statusCode != 200 {
                self.error = "Server error: \(httpResponse.statusCode)"
            } else {
                let decoder = JSONDecoder()
                comparison = try decoder.decode(ComparisonDetail.self, from: data)
            }
        } catch {
            self.error = error.localizedDescription
        }

        isLoading = false
    }

    private func rerunComparison(_ comparison: ComparisonDetail) async {
        logger.info("Re-running comparison with prompt: \(comparison.prompt.prefix(50))")
        // In the future, this would trigger a new comparison with the same settings
    }
}

// MARK: - Badge View

private struct Badge: View {
    let text: String
    let color: Color
    let icon: String

    var body: some View {
        HStack(spacing: 4) {
            Image(systemName: icon)
                .font(.caption2)
            Text(text)
                .font(.caption2)
        }
        .padding(.horizontal, 6)
        .padding(.vertical, 3)
        .background(color.opacity(0.15))
        .foregroundStyle(color)
        .cornerRadius(4)
    }
}

#Preview {
    ComparisonDetailView(
        comparisonSummary: ComparisonSummary(
            prompt: "What is the meaning of life?",
            modelsCompared: ["gpt-4o", "claude-3-5-sonnet-20241022"],
            totalCostUsd: 0.0042,
            comparisonId: "test-123",
            timestamp: "2024-01-25T14:30:00Z"
        )
    )
    .environmentObject(APIClient())
    .frame(width: 800, height: 600)
}
