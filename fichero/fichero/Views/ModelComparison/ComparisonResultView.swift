import SwiftUI

struct ComparisonResultView: View {
    let result: ComparisonResult

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                summaryHeader

                Divider()

                LazyVGrid(columns: gridColumns, spacing: 16) {
                    ForEach(result.results) { modelResult in
                        ModelResultCard(
                            result: modelResult,
                            isFastest: result.fastestModel == modelResult.id,
                            isCheapest: result.cheapestModel == modelResult.id
                        )
                    }
                }
            }
            .padding()
        }
        .navigationTitle("Comparison Results")
    }

    private var gridColumns: [GridItem] {
        [GridItem(.adaptive(minimum: 400, maximum: 600), spacing: 16)]
    }

    private var summaryHeader: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Prompt")
                .font(.headline)

            Text(result.prompt)
                .font(.body)
                .padding()
                .background(.quaternary.opacity(0.3))
                .cornerRadius(8)

            HStack(spacing: 24) {
                StatBadge(
                    label: "Models",
                    value: "\(result.modelsCompared.count)",
                    icon: "cpu"
                )

                StatBadge(
                    label: "Total Cost",
                    value: String(format: "$%.4f", result.totalCostUsd),
                    icon: "dollarsign.circle"
                )

                StatBadge(
                    label: "Total Time",
                    value: String(format: "%.0fms", result.totalLatencyMs),
                    icon: "clock"
                )

                if let fastest = result.fastestModel {
                    StatBadge(
                        label: "Fastest",
                        value: fastest.split(separator: "/").last.map(String.init) ?? fastest,
                        icon: "bolt.fill"
                    )
                }
            }
        }
    }
}

struct StatBadge: View {
    let label: String
    let value: String
    let icon: String

    var body: some View {
        HStack(spacing: 6) {
            Image(systemName: icon)
                .foregroundStyle(.secondary)

            VStack(alignment: .leading, spacing: 2) {
                Text(label)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                Text(value)
                    .font(.subheadline)
                    .fontWeight(.medium)
            }
        }
        .padding(8)
        .background(.quaternary.opacity(0.5))
        .cornerRadius(6)
    }
}
