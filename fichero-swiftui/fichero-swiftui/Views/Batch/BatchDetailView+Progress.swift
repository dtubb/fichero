import SwiftUI

extension BatchDetailView {
    @ViewBuilder
    var progressSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Progress")
                .font(.headline)

            VStack(alignment: .leading, spacing: 8) {
                ProgressView(value: displayBatch.progressPercent, total: 100)
                    .progressViewStyle(.linear)
                    .scaleEffect(y: 2, anchor: .center)

                HStack {
                    Text("\(displayBatch.completedItems) completed")
                        .foregroundStyle(.green)

                    if displayBatch.failedItems > 0 {
                        Text("/ \(displayBatch.failedItems) failed")
                            .foregroundStyle(.red)
                    }

                    Text("/ \(displayBatch.totalItems) total")
                        .foregroundStyle(.secondary)

                    Spacer()

                    Text(String(format: "%.1f%%", displayBatch.progressPercent))
                        .font(.headline)
                        .fontWeight(.bold)
                }
                .font(.subheadline)
            }

            LazyVGrid(columns: [
                GridItem(.flexible()),
                GridItem(.flexible()),
                GridItem(.flexible()),
                GridItem(.flexible())
            ], spacing: 12) {
                statCard("Total", "\(displayBatch.totalItems)", .blue)
                statCard("Completed", "\(displayBatch.completedItems)", .green)
                statCard("Failed", "\(displayBatch.failedItems)", .red)
                let pendingCount = displayBatch.totalItems - displayBatch.completedItems - displayBatch.failedItems
                statCard("Pending", "\(pendingCount)", .gray)
            }
        }
    }

    @ViewBuilder
    func statCard(_ title: String, _ value: String, _ color: Color) -> some View {
        VStack(spacing: 4) {
            Text(value)
                .font(.title2)
                .fontWeight(.bold)
                .foregroundStyle(color)
            Text(title)
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
        .padding(12)
        .background(color.opacity(0.1))
        .cornerRadius(8)
    }
}
