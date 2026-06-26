import SwiftUI

// MARK: - Badge View

struct Badge: View {
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

// MARK: - View Sections

extension ComparisonDetailView {

    // MARK: - Error View

    @ViewBuilder
    func errorView(_ message: String) -> some View {
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
    func comparisonContent(_ comparison: ComparisonDetail) -> some View {
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
    func headerSection(_ comparison: ComparisonDetail) -> some View {
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
    func promptSection(_ comparison: ComparisonDetail) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Prompt")
                .font(.headline)

            Text(comparison.prompt)
                .font(.body)
                .padding(12)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Color(platformColor: .textBackgroundColor))
                .cornerRadius(8)
                .textSelection(.enabled)
        }
    }

    // MARK: - Stats Section

    @ViewBuilder
    func statsSection(_ comparison: ComparisonDetail) -> some View {
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
    func statCard(title: String, value: String, icon: String, color: Color = .blue) -> some View {
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
        .background(Color(platformColor: .controlBackgroundColor))
        .cornerRadius(8)
    }

    // MARK: - Responses Section

    @ViewBuilder
    func responsesSection(_ comparison: ComparisonDetail) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Responses")
                .font(.headline)

            ForEach(comparison.results) { result in
                modelResponseCard(result, comparison: comparison)
            }
        }
    }

    @ViewBuilder
    // swiftlint:disable:next function_body_length
    func modelResponseCard(_ result: ModelResultDetail, comparison: ComparisonDetail) -> some View {
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
        .background(Color(platformColor: .controlBackgroundColor))
        .cornerRadius(12)
    }

    @ViewBuilder
    func providerIcon(_ provider: String) -> some View {
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
}
