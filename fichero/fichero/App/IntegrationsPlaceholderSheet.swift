import SwiftUI

// MARK: - Integrations Placeholder Sheet

/// Placeholder sheet for integrations features (coming soon)
struct IntegrationsPlaceholderSheet: View {
    @Environment(\.dismiss) private var dismiss

    let title: String
    let description: String
    let icon: String

    var body: some View {
        VStack(spacing: 24) {
            IntegrationsPlaceholderContent(title: title, description: description, icon: icon)

            Button("Close") {
                dismiss()
            }
            .buttonStyle(.borderedProminent)
        }
        .padding(40)
        .frame(width: 400, height: 350)
    }
}

struct IntegrationsPlaceholderContent: View {
    let title: String
    let description: String
    let icon: String

    var body: some View {
        VStack(spacing: 24) {
            Image(systemName: icon)
                .font(.system(size: 48))
                .foregroundStyle(.secondary)

            Text(title)
                .font(.title2)
                .fontWeight(.semibold)

            Text(description)
                .font(.body)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .frame(maxWidth: 300)

            VStack(spacing: 8) {
                Text("Coming Soon")
                    .font(.headline)
                    .foregroundStyle(.orange)

                Text("This feature is planned for a future release.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            .padding()
            .background(.orange.opacity(0.1))
            .clipShape(RoundedRectangle(cornerRadius: 8))
        }
        .frame(maxWidth: .infinity)
    }
}
