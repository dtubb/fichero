import SwiftUI
import FicheroAPIClient

/// Displays provider logo - uses bundled image if available, SF Symbol as fallback
struct ProviderLogoView: View {
    let entry: Components.Schemas.ProviderCatalogResponse
    let size: CGFloat

    var body: some View {
        Group {
            if let logoAsset = entry.logoAsset {
                // Use bundled logo image (SwiftUI loads directly from asset catalog)
                Image(logoAsset)
                    .resizable()
                    .aspectRatio(contentMode: .fit)
            } else {
                // Fallback to SF Symbol
                Image(systemName: entry.icon)
                    .font(.system(size: size * 0.7))
                    .foregroundColor(entry.swiftUIColor)
            }
        }
        .frame(width: size, height: size)
    }
}

// MARK: - Preview

#Preview {
    let mockProvider = Components.Schemas.ProviderCatalogResponse(
        key: "openai",
        displayName: "OpenAI",
        icon: "sparkles",
        color: "#10A37F",
        logoAsset: nil,
        baseURL: "https://api.openai.com/v1",
        authType: "bearer",
        apiKeyEnvVar: "OPENAI_API_KEY"
    )

    HStack(spacing: 20) {
        ProviderLogoView(entry: mockProvider, size: 32)
        ProviderLogoView(entry: mockProvider, size: 48)
        ProviderLogoView(entry: mockProvider, size: 64)
    }
    .padding()
}
