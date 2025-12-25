import SwiftUI

/// A reusable section header component for the sidebar
struct SectionHeader: View {
    let title: String
    let icon: String

    var body: some View {
        Label(title, systemImage: icon)
            .font(.subheadline)
            .fontWeight(.semibold)
            .foregroundColor(.secondary)
    }
}

#Preview {
    SectionHeader(title: "Library", icon: "folder")
        .padding()
        .previewLayout(.sizeThatFits)
}