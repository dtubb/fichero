import SwiftUI

extension BatchDetailView {
    @ViewBuilder
    func itemsSection(_ items: [BatchItemInfo]) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("Items")
                    .font(.headline)

                Spacer()

                Text("\(items.count) items")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            ForEach(items) { item in
                itemRow(item)
            }
        }
    }

    @ViewBuilder
    func itemRow(_ item: BatchItemInfo) -> some View {
        HStack(spacing: 12) {
            Circle()
                .fill(itemStatusColor(item.status))
                .frame(width: 10, height: 10)

            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Text("#\(item.itemIndex)")
                        .font(.subheadline)
                        .fontWeight(.medium)

                    Text(item.status.capitalized)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                if let inputs = item.inputs, !inputs.isEmpty {
                    Text(inputs.map { "\($0.key): \($0.value)" }.joined(separator: ", "))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }

                if let error = item.error {
                    Text(error)
                        .font(.caption)
                        .foregroundStyle(.red)
                        .lineLimit(2)
                }
            }

            Spacer()

            VStack(alignment: .trailing, spacing: 2) {
                if let started = item.startedAt {
                    Text(started)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
                if let completed = item.completedAt {
                    Text(completed)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }
        }
        .padding(10)
        .background(Color(nsColor: .controlBackgroundColor))
        .cornerRadius(8)
    }

    func itemStatusColor(_ status: String) -> Color {
        switch status {
        case "completed": return .green
        case "running": return .blue
        case "pending": return .gray
        case "failed": return .red
        default: return .secondary
        }
    }
}
