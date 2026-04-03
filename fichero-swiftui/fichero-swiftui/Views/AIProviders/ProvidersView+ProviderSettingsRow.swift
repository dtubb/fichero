import FicheroAPIClient
import SwiftUI

struct ProviderSettingsRow: View {
    let provider: Components.Schemas.ProviderResponse
    let catalogEntry: Components.Schemas.ProviderCatalogResponse?

    private var isLocalProvider: Bool {
        catalogEntry?.isLocal ?? false
    }

    var body: some View {
        HStack(spacing: 10) {
            if let entry = catalogEntry {
                ProviderLogoView(entry: entry, size: 28)
            } else {
                ZStack {
                    RoundedRectangle(cornerRadius: 4)
                        .fill(Color.accentColor.opacity(0.15))
                        .frame(width: 28, height: 28)

                    Image(systemName: "cpu")
                        .font(.caption)
                        .foregroundColor(.accentColor)
                }
            }

            VStack(alignment: .leading, spacing: 1) {
                Text(provider.name)
                    .font(.body)

                Text(provider.providerType)
                    .font(.caption)
                    .foregroundColor(.secondary)
            }

            Spacer()

            Circle()
                .fill(isLocalProvider || provider.hasApiKey ? Color.green : Color.orange)
                .frame(width: 8, height: 8)
        }
        .padding(.vertical, 2)
    }
}
