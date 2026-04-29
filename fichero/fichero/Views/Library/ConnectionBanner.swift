import SwiftUI

/// Banner shown when the backend API is unreachable.
struct ConnectionBanner: View {
    let error: Error?
    let onRetry: () -> Void

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: "exclamationmark.triangle.fill")
                .foregroundStyle(.yellow)

            Text(error?.localizedDescription ?? "Cannot connect to backend")
                .font(.callout)
                .lineLimit(1)

            Spacer()

            Button("Retry") {
                onRetry()
            }
            .buttonStyle(.bordered)
            .controlSize(.small)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background(.ultraThinMaterial)
    }
}
