import SwiftUI

/// Displays provider logo - uses bundled image if available, SF Symbol as fallback
struct ProviderLogoView: View {
    let entry: ProviderCatalogEntry
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
