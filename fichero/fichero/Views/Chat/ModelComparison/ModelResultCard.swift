import SwiftUI

struct ModelResultCard: View {
    let result: ModelResult
    let isFastest: Bool
    let isCheapest: Bool

    @State private var isExpanded = true

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                VStack(alignment: .leading) {
                    HStack {
                        Text(result.model)
                            .font(.headline)

                        if isFastest {
                            Image(systemName: "bolt.fill")
                                .foregroundStyle(.yellow)
                                .help("Fastest response")
                        }

                        if isCheapest {
                            Image(systemName: "dollarsign.circle.fill")
                                .foregroundStyle(.green)
                                .help("Lowest cost")
                        }
                    }

                    Text(result.provider)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                Spacer()

                VStack(alignment: .trailing) {
                    Text(String(format: "%.0fms", result.latencyMs))
                        .font(.caption)
                        .foregroundStyle(.secondary)

                    Text(String(format: "$%.4f", result.costUsd))
                        .font(.caption)
                        .foregroundStyle(.green)
                }
            }

            if let error = result.error {
                Text(error)
                    .font(.body)
                    .foregroundStyle(.red)
                    .padding()
                    .background(.red.opacity(0.1))
                    .cornerRadius(6)
            } else {
                Text(result.response)
                    .font(.body)
                    .padding()
                    .background(.quaternary.opacity(0.3))
                    .cornerRadius(6)
                    .lineLimit(isExpanded ? nil : 5)
                    .onTapGesture {
                        withAnimation {
                            isExpanded.toggle()
                        }
                    }
            }

            HStack {
                Label("\(result.inputTokens) in", systemImage: "arrow.down.circle")
                Label("\(result.outputTokens) out", systemImage: "arrow.up.circle")
            }
            .font(.caption2)
            .foregroundStyle(.secondary)
        }
        .padding()
        .background(.background)
        .cornerRadius(12)
        .shadow(color: .black.opacity(0.1), radius: 4, y: 2)
    }
}
