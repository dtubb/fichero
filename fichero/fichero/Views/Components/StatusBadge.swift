import SwiftUI

/// Colored status badge showing document processing status
struct StatusBadge: View {
    let status: Status

    var body: some View {
        HStack(spacing: 4) {
            Circle()
                .fill(statusColor)
                .frame(width: 6, height: 6)

            Text(status.rawValue.capitalized)
                .font(.caption2)
        }
        .padding(.horizontal, 6)
        .padding(.vertical, 3)
        .background(statusColor.opacity(0.15))
        .cornerRadius(10)
    }

    private var statusColor: Color {
        switch status {
        case .pending: return .gray
        case .processing: return .blue
        case .completed: return .green
        case .failed: return .red
        }
    }
}

// MARK: - Preview

#Preview {
    VStack(spacing: 12) {
        StatusBadge(status: .pending)
        StatusBadge(status: .processing)
        StatusBadge(status: .completed)
        StatusBadge(status: .failed)
    }
    .padding()
}
