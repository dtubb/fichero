import SwiftUI

/// Coming-soon panel the settings panes show for integrations that are planned but not built.
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

#Preview {
    IntegrationsPlaceholderContent(
        title: "Integrations",
        description: "Connect Fichero to the tools you already use.",
        icon: "puzzlepiece.extension"
    )
    .padding()
}
